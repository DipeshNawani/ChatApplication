import json
import os
from pathlib import Path


SETTINGS_PATH = Path(os.getenv("APPDATA", Path.home())) / "QuantumBytesChat" / "settings.json"
DEFAULT_SETTINGS = {"server_url": "http://127.0.0.1:8000", "username": ""}


def load_settings() -> dict[str, str]:
    try:
        values = json.loads(SETTINGS_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        values = {}
    return {
        "server_url": str(values.get("server_url", DEFAULT_SETTINGS["server_url"])),
        "username": str(values.get("username", DEFAULT_SETTINGS["username"])),
    }


def save_settings(server_url: str, username: str) -> None:
    SETTINGS_PATH.parent.mkdir(parents=True, exist_ok=True)
    SETTINGS_PATH.write_text(
        json.dumps({"server_url": server_url.strip(), "username": username.strip()}, indent=2),
        encoding="utf-8",
    )