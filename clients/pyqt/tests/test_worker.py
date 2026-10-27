import os
import socket
import sys
import tempfile
import threading
import time
from pathlib import Path

os.environ["JWT_SECRET"] = "phase3-test-secret-0123456789abcdef"
sys.path.insert(0, str(Path(__file__).parents[3] / "server"))

import pytest
import uvicorn
from PyQt6.QtCore import QCoreApplication

from app import main
from app.database import configure_database, dispose_database, get_user_by_username, init_database, save_message
from clients.pyqt.network_worker import SocketWorker


SECRET = "phase3-test-secret-0123456789abcdef"


@pytest.fixture
def qt_app() -> QCoreApplication:
    return QCoreApplication.instance() or QCoreApplication([])


def wait_for_port(port: int, timeout: float = 5) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.2):
                return
        except OSError:
            time.sleep(0.05)
    raise TimeoutError(f"port {port} did not open")


def start_server(port: int) -> tuple[uvicorn.Server, threading.Thread]:
    server = uvicorn.Server(uvicorn.Config(main.socket_app, host="127.0.0.1", port=port, log_level="error"))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    wait_for_port(port)
    return server, thread


def wait_until(app: QCoreApplication, predicate, timeout: float = 8) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        app.processEvents()
        if predicate():
            return True
        time.sleep(0.05)
    return False


def stop_worker(app: QCoreApplication, worker: SocketWorker) -> None:
    worker.stop()
    worker.wait(3000)
    app.processEvents()


@pytest.fixture
def running_server(tmp_path):
    main.DEV_MODE = True
    main.JWT_SECRET = SECRET
    configure_database(str(tmp_path / "worker.db"))
    init_database(create_schema=True)
    server, thread = start_server(8766)
    yield
    server.should_exit = True
    thread.join(3)
    dispose_database()


def test_worker_send_receive(running_server, qt_app: QCoreApplication) -> None:
    worker = SocketWorker("http://127.0.0.1:8766", "worker")
    received: list[dict] = []
    worker.message_received.connect(received.append)
    worker.start()
    worker.join_room("general")
    assert wait_until(qt_app, lambda: worker._client is not None and worker._client.connected)
    worker.send_message("general", "send-receive-id", "hello")
    assert wait_until(qt_app, lambda: any(payload.get("data", {}).get("text") == "hello" for payload in received))
    stop_worker(qt_app, worker)


def test_worker_reconnect_resends_pending_message(qt_app: QCoreApplication) -> None:
    with tempfile.TemporaryDirectory() as temporary_directory:
        main.DEV_MODE = True
        main.JWT_SECRET = SECRET
        configure_database(str(Path(temporary_directory) / "reconnect.db"))
        init_database(create_schema=True)
        worker = SocketWorker("http://127.0.0.1:8767", "reconnector")
        received: list[dict] = []
        states: list[str] = []
        worker.message_received.connect(received.append)
        worker.connection_state_changed.connect(states.append)
        worker.start()
        worker.join_room("general")
        assert wait_until(qt_app, lambda: "Offline" in states)
        worker.send_message("general", "reconnect-id", "queued before reconnect")
        server, thread = start_server(8767)
        try:
            assert wait_until(qt_app, lambda: any(payload.get("data", {}).get("text") == "queued before reconnect" for payload in received), 12)
        finally:
            stop_worker(qt_app, worker)
            server.should_exit = True
            thread.join(3)
            dispose_database()


def test_worker_duplicate_ack_does_not_create_second_message(running_server, qt_app: QCoreApplication) -> None:
    worker = SocketWorker("http://127.0.0.1:8766", "worker")
    received: list[dict] = []
    acknowledgements: list[dict] = []
    worker.message_received.connect(received.append)
    worker.message_acknowledged.connect(acknowledgements.append)
    worker.start()
    worker.join_room("general")
    assert wait_until(qt_app, lambda: worker._client is not None and worker._client.connected)
    user = get_user_by_username("worker")
    save_message("general", user.id, "duplicate-id", "text", "already saved")
    worker.send_message("general", "duplicate-id", "already saved")
    assert wait_until(qt_app, lambda: any(payload.get("data", {}).get("duplicate") is True for payload in acknowledgements))
    assert not received
    stop_worker(qt_app, worker)
