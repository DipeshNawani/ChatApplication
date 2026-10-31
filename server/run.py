"""Start the backend with its environment and migrations from any directory."""
import os
import errno
import json
from pathlib import Path
import socket
import sys
from urllib.error import URLError
from urllib.request import ProxyHandler, build_opener

from dotenv import load_dotenv


def check_existing_server(host: str, port: int) -> bool:
    """Detect another chat backend without stopping or replacing its process."""
    address = "127.0.0.1" if host in {"0.0.0.0", ""} else "::1" if host == "::" else host
    url_host = f"[{address}]" if ":" in address else address
    base_url = f"http://{url_host}:{port}"
    family = socket.AF_INET6 if ":" in host else socket.AF_INET
    try:
        with socket.socket(family, socket.SOCK_STREAM) as listener:
            listener.bind((host, port))
        return False
    except OSError as error:
        if error.errno not in {errno.EADDRINUSE, 10048} and getattr(error, "winerror", None) != 10048:
            raise
    try:
        opener = build_opener(ProxyHandler({}))
        with opener.open(f"{base_url}/health", timeout=2) as response:
            healthy = json.load(response).get("status") == "ok"
        with opener.open(f"{base_url}/openapi.json", timeout=2) as response:
            is_chat = json.load(response).get("info", {}).get("title") == "QuantumBytes Chat Server"
        if healthy and is_chat:
            print(f"Chat backend is already running at {base_url}. Use this address in both clients; no second server is needed.", flush=True)
            return True
    except (OSError, URLError, ValueError, AttributeError):
        pass
    raise SystemExit(f"Port {port} is already in use, but {base_url} is not a healthy QuantumBytes backend. Close the application using that port, or choose a different PORT in server/.env.")


def main() -> None:
    server_directory = Path(__file__).resolve().parent
    project_directory = server_directory.parent
    load_dotenv(server_directory / ".env", override=False)
    os.chdir(project_directory)
    if str(server_directory) not in sys.path:
        sys.path.insert(0, str(server_directory))
    if check_existing_server(os.getenv("HOST", "127.0.0.1"), int(os.getenv("PORT", "8000"))):
        return
    if len(os.getenv("JWT_SECRET", "")) < 32:
        raise SystemExit("JWT_SECRET must be at least 32 characters. Configure server/.env before starting the backend.")

    from alembic import command
    from alembic.config import Config
    from app.config import DATABASE_PATH, HOST, PORT

    if "://" not in DATABASE_PATH:
        Path(DATABASE_PATH).parent.mkdir(parents=True, exist_ok=True)
    migrations = Config(str(server_directory / "alembic.ini"))
    migrations.set_main_option("script_location", str(server_directory / "alembic"))
    command.upgrade(migrations, "head")

    import uvicorn
    from app.main import socket_app

    print(f"Starting chat backend at http://{HOST}:{PORT} (keep this process running)", flush=True)
    uvicorn.run(socket_app, host=HOST, port=PORT)


if __name__ == "__main__":
    main()
