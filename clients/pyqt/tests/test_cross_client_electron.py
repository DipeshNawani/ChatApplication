import asyncio
import os
import socket
import subprocess
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path

import pytest
import uvicorn
from PyQt6.QtCore import QCoreApplication

os.environ["JWT_SECRET"] = "cross-client-tests-secret-0123456789"
sys.path.insert(0, str(Path(__file__).parents[3] / "server"))

from app import auth, main
from app.database import add_member, configure_database, create_group_room, create_user, dispose_database, get_or_create_direct_room, init_database
from clients.pyqt.network_worker import SocketWorker


SECRET = "cross-client-tests-secret-0123456789"


def unused_port() -> int:
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        return int(listener.getsockname()[1])


@pytest.fixture
def qt_app() -> QCoreApplication:
    return QCoreApplication.instance() or QCoreApplication([])


def wait_for_port(port: int, timeout: float = 6) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{port}/health", timeout=0.2) as response:
                if response.status == 200:
                    return
        except (OSError, urllib.error.URLError):
            time.sleep(0.05)
    raise TimeoutError(f"port {port} did not open")


def wait_until(app: QCoreApplication, predicate, timeout: float = 8) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        app.processEvents()
        if predicate():
            return True
        time.sleep(0.05)
    return False


async def read_probe(process: asyncio.subprocess.Process, predicate, timeout: float = 6) -> dict:
    deadline = asyncio.get_running_loop().time() + timeout
    while asyncio.get_running_loop().time() < deadline:
        line = await asyncio.wait_for(process.stdout.readline(), timeout=max(0.1, deadline - asyncio.get_running_loop().time()))
        if not line:
            raise AssertionError("Electron socket probe exited unexpectedly")
        import json
        value = json.loads(line.decode("utf-8"))
        if value.get("type") == "probe_error":
            raise AssertionError(f"Electron probe request failed: {value.get('message')}")
        if predicate(value):
            return value
    raise TimeoutError("Expected Electron socket event was not received")


def test_pyqt_and_electron_interoperate_direct_group_history_reconnect(qt_app: QCoreApplication, tmp_path: Path) -> None:
    async def case() -> None:
        main.DEV_MODE = False
        main.JWT_SECRET = SECRET
        auth.JWT_SECRET = SECRET
        configure_database(str(tmp_path / "cross-client.db"))
        init_database(create_schema=True)
        alice = create_user("alice", auth.hash_password("password-123"))
        electron_user = create_user("electronuser", auth.hash_password("password-123"))
        direct_room, _ = get_or_create_direct_room(alice.id, electron_user.id)
        group_room = create_group_room(alice.id, "Cross Client Group")
        assert add_member(group_room.id, electron_user.id)

        port = unused_port()
        server = uvicorn.Server(uvicorn.Config(main.socket_app, host="127.0.0.1", port=port, log_level="error"))
        server_thread = threading.Thread(target=server.run, daemon=True)
        server_thread.start()
        wait_for_port(port)

        electron = await asyncio.create_subprocess_exec(
            "node",
            "clients/electron/test/socket-probe.js",
            f"http://127.0.0.1:{port}",
            auth.create_access_token(electron_user),
            cwd=Path(__file__).parents[3],
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        pyqt = SocketWorker(f"http://127.0.0.1:{port}", "alice", auth.create_access_token(alice))
        pyqt_received: list[dict] = []
        pyqt.connection_state_changed.connect(lambda _state: None)
        pyqt.message_received.connect(pyqt_received.append)
        pyqt.start()
        pyqt.join_room(direct_room.id)

        try:
            connected = await read_probe(electron, lambda item: item.get("type") == "connected")
            assert connected["type"] == "connected"
            electron.stdin.write((__import__("json").dumps({"op": "join", "roomId": direct_room.id}) + "\n").encode())
            await electron.stdin.drain()
            await read_probe(electron, lambda item: item.get("type") == "event" and item.get("event") == "room:joined" and item["payload"]["data"]["room_id"] == direct_room.id)

            electron.stdin.write((__import__("json").dumps({"op": "emit", "event": "message:send", "payload": {"data": {"room_id": direct_room.id, "client_message_id": "electron-direct-1", "kind": "text", "text": "from Electron"}, "request_id": "electron-direct-1"}}) + "\n").encode())
            await electron.stdin.drain()
            assert wait_until(qt_app, lambda: any(item["data"].get("text") == "from Electron" for item in pyqt_received))
            pyqt.send_message(direct_room.id, "pyqt-direct-1", "reply from PyQt")
            await read_probe(electron, lambda item: item.get("type") == "event" and item.get("event") == "message:created" and item["payload"]["data"].get("text") == "reply from PyQt")
            electron.stdin.write((__import__("json").dumps({"op": "history", "roomId": direct_room.id}) + "\n").encode())
            await electron.stdin.drain()
            history = await read_probe(electron, lambda item: item.get("type") == "history" and item.get("roomId") == direct_room.id)
            assert {item["text"] for item in history["payload"]["messages"]} >= {"from Electron", "reply from PyQt"}

            allowed_file = tmp_path / "cross-client.txt"
            allowed_file.write_text("shared from Electron", encoding="utf-8")
            electron.stdin.write((__import__("json").dumps({"op": "upload", "filePath": str(allowed_file)}) + "\n").encode())
            await electron.stdin.drain()
            upload = await read_probe(electron, lambda item: item.get("type") == "upload")
            assert upload["status"] == 200
            uploaded = upload["payload"]["file"]
            electron.stdin.write((__import__("json").dumps({"op": "emit", "event": "message:send", "payload": {"data": {"room_id": direct_room.id, "client_message_id": "electron-file-1", "kind": "file", "text": "", "file_id": uploaded["file_id"]}, "request_id": "electron-file-1"}}) + "\n").encode())
            await electron.stdin.drain()
            assert wait_until(qt_app, lambda: any((item["data"].get("file") or {}).get("file_id") == uploaded["file_id"] for item in pyqt_received))

            too_large = tmp_path / "too-large.txt"
            too_large.write_bytes(b"x" * (5 * 1024 * 1024 + 1))
            electron.stdin.write((__import__("json").dumps({"op": "upload", "filePath": str(too_large)}) + "\n").encode())
            await electron.stdin.drain()
            rejected_upload = await read_probe(electron, lambda item: item.get("type") == "upload" and item.get("status") == 413, timeout=15)
            assert rejected_upload["payload"]["error"]["code"] == "FILE_TOO_LARGE"

            pyqt.join_room(group_room.id)
            assert wait_until(qt_app, lambda: group_room.id in pyqt._joined_rooms, 4)
            electron.stdin.write((__import__("json").dumps({"op": "join", "roomId": group_room.id}) + "\n").encode())
            await electron.stdin.drain()
            await read_probe(electron, lambda item: item.get("type") == "event" and item.get("event") == "room:joined" and item["payload"]["data"]["room_id"] == group_room.id)
            pyqt.send_message(group_room.id, "pyqt-group-1", "from PyQt")
            await read_probe(electron, lambda item: item.get("type") == "event" and item.get("event") == "message:created" and item["payload"]["data"].get("text") == "from PyQt")
            electron.stdin.write((__import__("json").dumps({"op": "emit", "event": "message:send", "payload": {"data": {"room_id": group_room.id, "client_message_id": "electron-group-1", "kind": "text", "text": "group from Electron"}, "request_id": "electron-group-1"}}) + "\n").encode())
            await electron.stdin.drain()
            assert wait_until(qt_app, lambda: any(item["data"].get("text") == "group from Electron" for item in pyqt_received))

            electron.stdin.write((__import__("json").dumps({"op": "disconnect"}) + "\n").encode())
            await electron.stdin.drain()
            await read_probe(electron, lambda item: item.get("type") == "disconnected")
            electron.stdin.write((__import__("json").dumps({"op": "connect"}) + "\n").encode())
            await electron.stdin.drain()
            await read_probe(electron, lambda item: item.get("type") == "connected")
            await read_probe(electron, lambda item: item.get("type") == "event" and item.get("event") == "room:joined" and item["payload"]["data"]["room_id"] == direct_room.id)

        finally:
            pyqt.stop()
            pyqt.wait(3000)
            electron.stdin.write(b'{"op":"exit"}\n')
            await electron.stdin.drain()
            try:
                await asyncio.wait_for(electron.wait(), timeout=4)
            except asyncio.TimeoutError:
                electron.kill()
                await electron.wait()
            server.should_exit = True
            server_thread.join(4)
            dispose_database()

    asyncio.run(case())
