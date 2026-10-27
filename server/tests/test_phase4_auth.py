import asyncio
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import jwt
import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).parents[1]))

from app import auth, database, main  # noqa: E402
from app.database import Membership, Room, Session, configure_database, get_user_by_username, init_database, save_message  # noqa: E402


@pytest.fixture
def api_client(tmp_path, monkeypatch):
    monkeypatch.setattr(main, "DEV_MODE", False)
    monkeypatch.setattr(main, "JWT_SECRET", "phase4-test-secret-0123456789abcdef")
    monkeypatch.setattr(auth, "JWT_SECRET", "phase4-test-secret-0123456789abcdef")
    monkeypatch.setattr(auth, "JWT_EXPIRE_MINUTES", 1)
    configure_database(str(tmp_path / "phase4.db"))
    init_database(create_schema=True)
    with TestClient(main.app) as client:
        yield client


def register(client: TestClient, username: str, password: str = "password-123") -> dict:
    response = client.post("/api/v1/auth/register", json={"username": username, "password": password})
    assert response.status_code == 201
    return response.json()


def test_wrong_password_is_generic(api_client: TestClient) -> None:
    register(api_client, "alice")
    response = api_client.post("/api/v1/auth/login", json={"username": "alice", "password": "wrong-pass"})
    assert response.status_code == 401
    assert response.json()["error"]["message"] == "Invalid username or password"


def test_expired_token_is_rejected(api_client: TestClient) -> None:
    user = register(api_client, "alice")["user"]
    token = jwt.encode(
        {"sub": str(user["user_id"]), "exp": datetime.now(timezone.utc) - timedelta(minutes=1)},
        "phase4-test-secret-0123456789abcdef",
        algorithm="HS256",
    )
    response = api_client.get("/api/v1/rooms", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 401


def test_non_member_cannot_read_history_or_join_socket_room(api_client: TestClient) -> None:
    register(api_client, "alice")
    bob = register(api_client, "bob")["user"]
    alice = get_user_by_username("alice")
    room = Room(id="private-room", name="private", kind="group", created_at=datetime.now(timezone.utc))
    with Session(database.engine) as session:
        session.add(room)
        session.add(Membership(room=room, user_id=alice.id, joined_at=datetime.now(timezone.utc)))
        session.commit()
    save_message("private-room", alice.id, "private-1", "text", "secret")
    token = auth.create_access_token(get_user_by_username("bob"))
    response = api_client.get("/api/v1/rooms/private-room/messages", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 403

    main.connected_users["non-member-sid"] = bob["user_id"]
    main.joined_rooms["non-member-sid"] = set()
    asyncio.run(main.room_join("non-member-sid", {"data": {"room_id": "private-room"}}))
    assert "private-room" not in main.joined_rooms["non-member-sid"]


def test_history_paginates_120_messages_by_sequence_id(api_client: TestClient) -> None:
    account = register(api_client, "alice")
    user = get_user_by_username("alice")
    for index in range(120):
        save_message("general", user.id, f"page-{index}", "text", f"message {index}")
    headers = {"Authorization": f"Bearer {account['access_token']}"}

    newest = api_client.get("/api/v1/rooms/general/messages", headers=headers)
    newest_body = newest.json()
    assert [item["sequence_id"] for item in newest_body["messages"]] == list(range(71, 121))
    assert newest_body["has_more"] is True
    assert newest_body["next_before"] == 71

    older = api_client.get("/api/v1/rooms/general/messages?before=71", headers=headers)
    older_body = older.json()
    assert [item["sequence_id"] for item in older_body["messages"]] == list(range(21, 71))
    assert older_body["has_more"] is True

    after = api_client.get("/api/v1/rooms/general/messages?after=0", headers=headers)
    after_body = after.json()
    assert [item["sequence_id"] for item in after_body["messages"]] == list(range(1, 51))
    assert after_body["has_more"] is True
    assert after_body["next_after"] == 50
