from types import SimpleNamespace

import pytest
import requests

from clients.pyqt import auth_client


@pytest.mark.parametrize("mode", ["login", "register"])
def test_unavailable_backend_has_actionable_error(monkeypatch, mode):
    def unavailable(*args, **kwargs):
        raise requests.ConnectionError("Connection refused")
    monkeypatch.setattr(auth_client.requests, "post", unavailable)
    worker = auth_client.AuthWorker(mode, "http://127.0.0.1:8000", "alice", "password-123")
    failures = []
    worker.failed.connect(failures.append)
    worker.run()
    assert failures[0]["code"] == "SERVER_UNREACHABLE"
    assert "start-server.ps1" in failures[0]["message"]
    assert "http://127.0.0.1:8000" in failures[0]["message"]


@pytest.mark.parametrize("mode", ["login", "register"])
def test_authentication_succeeds_for_both_actions(monkeypatch, mode):
    result = {"access_token": "test-token", "user": {"username": "alice"}}
    def success(url, **kwargs):
        assert url == f"http://127.0.0.1:8000/api/v1/auth/{mode}"
        assert kwargs["json"] == {"username": "alice", "password": "password-123"}
        return SimpleNamespace(ok=True, json=lambda: result)
    monkeypatch.setattr(auth_client.requests, "post", success)
    worker = auth_client.AuthWorker(mode, "127.0.0.1:8000/", "alice", "password-123")
    successes = []
    worker.succeeded.connect(successes.append)
    worker.run()
    assert successes == [result]


@pytest.mark.parametrize("address", ["", "http://", "file:///server", "http://user:secret@example.com", "http://example.com:bad"])
def test_invalid_server_address_is_rejected(address):
    with pytest.raises(ValueError):
        auth_client.normalize_server_url(address)


def test_wrong_server_response_is_reported(monkeypatch):
    def invalid_json():
        raise ValueError("HTML response")
    monkeypatch.setattr(auth_client.requests, "post", lambda *args, **kwargs: SimpleNamespace(ok=False, status_code=502, json=invalid_json))
    worker = auth_client.AuthWorker("login", "http://127.0.0.1:8000", "alice", "password-123")
    failures = []
    worker.failed.connect(failures.append)
    worker.run()
    assert failures[0]["code"] == "INVALID_SERVER_RESPONSE"
