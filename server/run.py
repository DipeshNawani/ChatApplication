import uvicorn

from app.config import HOST, PORT
from app.main import socket_app


if __name__ == "__main__":
    uvicorn.run(socket_app, host=HOST, port=PORT)