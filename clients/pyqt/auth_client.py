import requests
from pathlib import Path
from PyQt6.QtCore import QThread, pyqtSignal


class AuthWorker(QThread):
    succeeded = pyqtSignal(dict)
    failed = pyqtSignal(dict)

    def __init__(self, mode: str, server_url: str, username: str = "", password: str = "", token: str = "", query: str = "") -> None:
        super().__init__()
        self.mode = mode
        self.server_url = server_url.rstrip("/")
        self.username = username
        self.password = password
        self.token = token
        self.query = query

    def run(self) -> None:
        try:
            timeout = 90 if self.mode in {"login", "register"} else 20
            if self.mode in {"login", "register"}:
                response = requests.post(
                    f"{self.server_url}/api/v1/auth/{self.mode}",
                    json={"username": self.username, "password": self.password},
                    timeout=timeout,
                )
            elif self.mode == "search":
                response = requests.get(
                    f"{self.server_url}/api/v1/users/search",
                    params={"q": self.query},
                    headers={"Authorization": f"Bearer {self.token}"},
                    timeout=timeout,
                )
            elif self.mode == "direct":
                response = requests.post(
                    f"{self.server_url}/api/v1/chats/direct",
                    json={"username": self.query},
                    headers={"Authorization": f"Bearer {self.token}"},
                    timeout=timeout,
                )
            elif self.mode == "rooms":
                response = requests.get(
                    f"{self.server_url}/api/v1/rooms",
                    headers={"Authorization": f"Bearer {self.token}"},
                    timeout=8,
                )
            elif self.mode == "group":
                response = requests.post(f"{self.server_url}/api/v1/rooms/groups", json={"name": self.query}, headers={"Authorization": f"Bearer {self.token}"}, timeout=timeout)
            elif self.mode == "member":
                response = requests.post(f"{self.server_url}/api/v1/rooms/{self.query}/members", json={"username": self.username}, headers={"Authorization": f"Bearer {self.token}"}, timeout=timeout)
            elif self.mode == "leave":
                response = requests.post(f"{self.server_url}/api/v1/rooms/{self.query}/leave", headers={"Authorization": f"Bearer {self.token}"}, timeout=timeout)
            elif self.mode == "upload":
                path = Path(self.query)
                with path.open("rb") as file_stream:
                    response = requests.post(
                        f"{self.server_url}/api/v1/files",
                        files={"file": (path.name, file_stream)},
                        headers={"Authorization": f"Bearer {self.token}"},
                        timeout=30,
                    )
            elif self.mode == "download":
                response = requests.get(
                    f"{self.server_url}/api/v1/files/{self.query}",
                    headers={"Authorization": f"Bearer {self.token}"},
                    timeout=30,
                )
                if response.ok:
                    self.succeeded.emit({"content": response.content})
                    return
            else:
                raise ValueError(f"Unknown auth request: {self.mode}")
            payload = response.json()
            if response.ok:
                self.succeeded.emit(payload)
            else:
                error = payload.get("error") or payload.get("detail") or payload
                if isinstance(error, str):
                    error = {"code": "REQUEST_FAILED", "message": error}
                self.failed.emit({"code": error.get("code", "REQUEST_FAILED"), "message": error.get("message", "Request failed")})
        except Exception as error:
            self.failed.emit({"code": "CONNECTION_ERROR", "message": str(error)})
