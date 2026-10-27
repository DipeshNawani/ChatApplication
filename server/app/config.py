import os
import re


# DEV_MODE is enabled only by pytest fixtures that monkeypatch app.main.DEV_MODE.
DEV_MODE = False
DATABASE_PATH = os.getenv("DATABASE_URL", os.getenv("DATABASE_PATH", "server/data/chat.db"))
HOST = os.getenv("HOST", "127.0.0.1")
PORT = int(os.getenv("PORT", "8000"))
MAX_MESSAGE_LENGTH = 4000
MAX_ROOM_ID_LENGTH = 64
PROTOCOL_VERSION = 1
JWT_SECRET = os.getenv("JWT_SECRET", "")
JWT_EXPIRE_MINUTES = int(os.getenv("JWT_EXPIRE_MINUTES", "60"))
TESTING = os.getenv("TESTING", "false").lower() == "true"
USERNAME_PATTERN = re.compile(r"^[A-Za-z0-9_-]{3,32}$")
RESERVED_USERNAMES = {"admin", "system", "server", "you"}
GENERAL_ROOM_ID = "general"
MAX_GROUP_MEMBERS = int(os.getenv("MAX_GROUP_MEMBERS", "50"))
MAX_FILE_SIZE = 5 * 1024 * 1024
UPLOAD_DIRECTORY = os.getenv("UPLOAD_DIRECTORY", "server/data/uploads")
ALLOWED_FILE_EXTENSIONS = {".png", ".jpg", ".gif", ".webp", ".pdf", ".txt"}
CORS_ORIGINS = [origin.strip() for origin in os.getenv("CORS_ORIGINS", "http://localhost,http://127.0.0.1").split(",") if origin.strip()]
TRUST_PROXY_HEADERS = os.getenv("TRUST_PROXY_HEADERS", "false").lower() == "true"
