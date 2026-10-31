import requests
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit
from PyQt6.QtCore import QThread, pyqtSignal


def normalize_server_url(value: str) -> str:
    value = value.strip()
    if not value:
        raise ValueError("Enter a server address, such as http://127.0.0.1:8000.")
    parts = urlsplit(value if "://" in value else f"http://{value}")
    if parts.scheme not in {"http", "https"} or not parts.hostname or any(character.isspace() for character in parts.netloc) or parts.username or parts.password or parts.query or parts.fragment:
        raise ValueError("Enter a valid server address, such as http://127.0.0.1:8000.")
    try:
        parts.port
    except ValueError as error:
        raise ValueError("The server port must be a number between 1 and 65535.") from error
    return urlunsplit(parts).rstrip("/")


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
            self.server_url = normalize_server_url(self.server_url)
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
            try:
                payload = response.json()
            except ValueError:
                self.failed.emit({"code": "INVALID_SERVER_RESPONSE", "message": f"The server did not return a chat API response (HTTP {response.status_code}). Check the server address."})
                return
            if response.ok:
                if self.mode in {"login", "register"} and (not isinstance(payload, dict) or not payload.get("access_token") or not isinstance(payload.get("user"), dict) or not payload["user"].get("username")):
                    self.failed.emit({"code": "INVALID_SERVER_RESPONSE", "message": "This address did not return a valid chat login response."})
                    return
                self.succeeded.emit(payload)
            else:
                error = (payload.get("error") or payload.get("detail") or payload) if isinstance(payload, dict) else "Request failed"
                if not isinstance(error, dict):
                    error = {"code": "REQUEST_FAILED", "message": str(error)}
                self.failed.emit({"code": error.get("code", "REQUEST_FAILED"), "message": error.get("message", "Request failed")})
        except requests.exceptions.SSLError:
            self.failed.emit({"code": "TLS_ERROR", "message": "The server certificate could not be verified. Check the HTTPS address and certificate."})
        except requests.exceptions.Timeout:
            self.failed.emit({"code": "SERVER_TIMEOUT", "message": f"The server at {self.server_url} took too long to respond. It may be starting up; please try again."})
        except requests.exceptions.ConnectionError:
            local = urlsplit(self.server_url).hostname in {"localhost", "127.0.0.1", "::1"}
            hint = "Start the backend with start-server.ps1, then try again." if local else "Check the server address and your network connection."
            self.failed.emit({"code": "SERVER_UNREACHABLE", "message": f"Cannot reach the chat server at {self.server_url}. {hint}"})
        except ValueError as error:
            self.failed.emit({"code": "INVALID_SERVER_URL", "message": str(error)})
        except Exception as error:
            self.failed.emit({"code": "CONNECTION_ERROR", "message": str(error)})
