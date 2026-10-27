from pathlib import Path
import sys

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).parents[1]))

from app import auth, database, main, routes  # noqa: E402
from app.database import get_user_by_username, save_message  # noqa: E402
from app.rate_limit import PerUserRateLimiter  # noqa: E402

SECRET = "phase5-file-tests-secret-0123456789"


@pytest.fixture
def file_client(tmp_path, monkeypatch):
    monkeypatch.setattr(main, "DEV_MODE", False)
    monkeypatch.setattr(main, "JWT_SECRET", SECRET)
    monkeypatch.setattr(auth, "JWT_SECRET", SECRET)
    monkeypatch.setattr(routes, "UPLOAD_DIRECTORY", str(tmp_path / "uploads"))
    monkeypatch.setattr(routes, "auth_rate_limiter", PerUserRateLimiter())
    database.configure_database(str(tmp_path / "files.db"))
    database.init_database(create_schema=True)
    with TestClient(main.app) as client:
        yield client
    database.dispose_database()


def register(client: TestClient, username: str) -> tuple[dict, str]:
    response = client.post("/api/v1/auth/register", json={"username": username, "password": "password-123"})
    assert response.status_code == 201
    value = response.json()
    return value["user"], value["access_token"]


def test_upload_accepts_allowed_utf8_text(file_client: TestClient) -> None:
    _, token = register(file_client, "alice")
    response = file_client.post(
        "/api/v1/files",
        headers={"Authorization": f"Bearer {token}"},
        files={"file": ("notes.txt", b"meeting notes", "text/plain")},
    )
    assert response.status_code == 200
    assert response.json()["file"]["size"] == len(b"meeting notes")


def test_upload_rejects_disallowed_extension(file_client: TestClient) -> None:
    _, token = register(file_client, "alice")
    response = file_client.post(
        "/api/v1/files",
        headers={"Authorization": f"Bearer {token}"},
        files={"file": ("payload.exe", b"MZfake", "application/octet-stream")},
    )
    assert response.status_code == 415
    assert response.json()["error"]["code"] == "FILE_TYPE_NOT_ALLOWED"


def test_upload_rejects_mismatched_content(file_client: TestClient) -> None:
    _, token = register(file_client, "alice")
    response = file_client.post(
        "/api/v1/files",
        headers={"Authorization": f"Bearer {token}"},
        files={"file": ("image.png", b"not a png", "image/png")},
    )
    assert response.status_code == 415
    assert response.json()["error"]["code"] == "FILE_CONTENT_INVALID"


def test_upload_rejects_file_over_five_megabytes(file_client: TestClient) -> None:
    _, token = register(file_client, "alice")
    response = file_client.post(
        "/api/v1/files",
        headers={"Authorization": f"Bearer {token}"},
        files={"file": ("large.txt", b"x" * (5 * 1024 * 1024 + 1), "text/plain")},
    )
    assert response.status_code == 413
    assert response.json()["error"]["code"] == "FILE_TOO_LARGE"


def test_download_requires_shared_room_membership(file_client: TestClient) -> None:
    owner, owner_token = register(file_client, "owner")
    member, member_token = register(file_client, "member")
    _, outsider_token = register(file_client, "outsider")
    room_id = file_client.post("/api/v1/rooms/groups", json={"name": "Files"}, headers={"Authorization": f"Bearer {owner_token}"}).json()["room"]["room_id"]
    file_info = file_client.post(
        "/api/v1/files",
        headers={"Authorization": f"Bearer {owner_token}"},
        files={"file": ("notes.txt", b"shared material", "text/plain")},
    ).json()["file"]
    file_client.post(f"/api/v1/rooms/{room_id}/members", json={"username": "member"}, headers={"Authorization": f"Bearer {owner_token}"})
    save_message(room_id, owner["user_id"], "file-share", "file", "", file_info["file_id"])
    allowed = file_client.get(f"/api/v1/files/{file_info['file_id']}", headers={"Authorization": f"Bearer {member_token}"})
    denied = file_client.get(f"/api/v1/files/{file_info['file_id']}", headers={"Authorization": f"Bearer {outsider_token}"})
    assert allowed.status_code == 200
    assert allowed.content == b"shared material"
    assert denied.status_code == 404
