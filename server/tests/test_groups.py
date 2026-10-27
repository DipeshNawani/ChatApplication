from datetime import datetime, timezone
from pathlib import Path
import sys

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

sys.path.insert(0, str(Path(__file__).parents[1]))

from app import auth, database, main, routes  # noqa: E402
from app.database import Membership, Room, get_user_by_username, save_message  # noqa: E402
from app.rate_limit import PerUserRateLimiter  # noqa: E402


SECRET = "group-tests-secret-0123456789abcdef"


@pytest.fixture
def group_client(tmp_path, monkeypatch):
    monkeypatch.setattr(main, "DEV_MODE", False)
    monkeypatch.setattr(main, "JWT_SECRET", SECRET)
    monkeypatch.setattr(auth, "JWT_SECRET", SECRET)
    monkeypatch.setattr(routes, "auth_rate_limiter", PerUserRateLimiter())
    database.configure_database(str(tmp_path / "groups.db"))
    database.init_database(create_schema=True)
    with TestClient(main.app) as client:
        yield client
    database.dispose_database()


def register(client: TestClient, username: str) -> tuple[dict, str]:
    response = client.post("/api/v1/auth/register", json={"username": username, "password": "password-123"})
    assert response.status_code == 201, response.json()
    result = response.json()
    return result["user"], result["access_token"]


def test_create_group_owner_and_initial_membership(group_client: TestClient) -> None:
    owner, token = register(group_client, "owner")
    response = group_client.post("/api/v1/rooms/groups", json={"name": "Study Group"}, headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 200
    room = response.json()["room"]
    assert room["kind"] == "group"
    assert room["owner_id"] == owner["user_id"]
    assert database.is_member(room["room_id"], owner["user_id"])


def test_group_add_member_and_join_sequence_hides_earlier_history(group_client: TestClient) -> None:
    owner, owner_token = register(group_client, "owner")
    member, member_token = register(group_client, "member")
    room_id = group_client.post("/api/v1/rooms/groups", json={"name": "Study Group"}, headers={"Authorization": f"Bearer {owner_token}"}).json()["room"]["room_id"]
    save_message(room_id, owner["user_id"], "before-add", "text", "not visible to new member")
    response = group_client.post(f"/api/v1/rooms/{room_id}/members", json={"username": "member"}, headers={"Authorization": f"Bearer {owner_token}"})
    assert response.status_code == 200
    save_message(room_id, owner["user_id"], "after-add", "text", "visible to new member")
    history = group_client.get(f"/api/v1/rooms/{room_id}/messages", headers={"Authorization": f"Bearer {member_token}"}).json()
    assert [message["text"] for message in history["messages"]] == ["visible to new member"]


def test_only_owner_can_add_group_members(group_client: TestClient) -> None:
    _, owner_token = register(group_client, "owner")
    _, member_token = register(group_client, "member")
    register(group_client, "third")
    room_id = group_client.post("/api/v1/rooms/groups", json={"name": "Study Group"}, headers={"Authorization": f"Bearer {owner_token}"}).json()["room"]["room_id"]
    group_client.post(f"/api/v1/rooms/{room_id}/members", json={"username": "member"}, headers={"Authorization": f"Bearer {owner_token}"})
    response = group_client.post(f"/api/v1/rooms/{room_id}/members", json={"username": "third"}, headers={"Authorization": f"Bearer {member_token}"})
    assert response.status_code == 403


def test_owner_leaving_transfers_ownership_to_oldest_member(group_client: TestClient) -> None:
    owner, owner_token = register(group_client, "owner")
    first, first_token = register(group_client, "first")
    second, second_token = register(group_client, "second")
    room_id = group_client.post("/api/v1/rooms/groups", json={"name": "Study Group"}, headers={"Authorization": f"Bearer {owner_token}"}).json()["room"]["room_id"]
    group_client.post(f"/api/v1/rooms/{room_id}/members", json={"username": "first"}, headers={"Authorization": f"Bearer {owner_token}"})
    group_client.post(f"/api/v1/rooms/{room_id}/members", json={"username": "second"}, headers={"Authorization": f"Bearer {owner_token}"})
    result = group_client.post(f"/api/v1/rooms/{room_id}/leave", headers={"Authorization": f"Bearer {owner_token}"}).json()
    assert result["owner_id"] == first["user_id"]
    assert database.get_room(room_id).owner_id == first["user_id"]


def test_last_member_leaves_and_closes_group(group_client: TestClient) -> None:
    _, owner_token = register(group_client, "owner")
    owner = get_user_by_username("owner")
    room_id = group_client.post("/api/v1/rooms/groups", json={"name": "Empty Group"}, headers={"Authorization": f"Bearer {owner_token}"}).json()["room"]["room_id"]
    result = group_client.post(f"/api/v1/rooms/{room_id}/leave", headers={"Authorization": f"Bearer {owner_token}"}).json()
    assert result["closed"] is True
    assert database.get_room(room_id).is_closed is True
    assert room_id not in {room["room_id"] for room in database.list_rooms(owner.id)}


def test_group_name_validation_and_member_cap(group_client: TestClient, monkeypatch) -> None:
    _, token = register(group_client, "owner")
    monkeypatch.setattr("app.routes.MAX_GROUP_MEMBERS", 1)
    response = group_client.post("/api/v1/rooms/groups", json={"name": ""}, headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 422
    room_id = group_client.post("/api/v1/rooms/groups", json={"name": "Solo"}, headers={"Authorization": f"Bearer {token}"}).json()["room"]["room_id"]
    register(group_client, "member")
    response = group_client.post(f"/api/v1/rooms/{room_id}/members", json={"username": "member"}, headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 409
