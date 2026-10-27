import asyncio
import socket
import sys
import tempfile
import time
from pathlib import Path

import pytest
import socketio
import uvicorn

sys.path.insert(0, str(Path(__file__).parents[1]))

from app import auth, main  # noqa: E402
from app.database import configure_database, create_user, dispose_database, init_database  # noqa: E402

SECRET = "phase5-socket-tests-secret-0123456789"


def wait_for_port(port: int, timeout: float = 6) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.2):
                return
        except OSError:
            time.sleep(0.05)
    raise TimeoutError(f"port {port} did not open")


async def event_case(callback) -> None:
    with tempfile.TemporaryDirectory() as temporary_directory:
        main.DEV_MODE = False
        main.JWT_SECRET = SECRET
        auth.JWT_SECRET = SECRET
        configure_database(str(Path(temporary_directory) / "events.db"))
        init_database(create_schema=True)
        alice = create_user("alice", auth.hash_password("password-123"))
        bob = create_user("bob", auth.hash_password("password-123"))
        alice_token = auth.create_access_token(alice)
        bob_token = auth.create_access_token(bob)
        server = uvicorn.Server(uvicorn.Config(main.socket_app, host="127.0.0.1", port=8769, log_level="error"))
        server_task = asyncio.create_task(server.serve())
        await asyncio.to_thread(wait_for_port, 8769)
        first = socketio.AsyncClient(reconnection=False)
        second = socketio.AsyncClient(reconnection=False)
        try:
            await first.connect("http://127.0.0.1:8769", auth={"token": alice_token})
            await second.connect("http://127.0.0.1:8769", auth={"token": bob_token})
            await callback(first, second)
        finally:
            await first.disconnect()
            await second.disconnect()
            server.should_exit = True
            await server_task
            dispose_database()


def test_typing_indicator_is_room_scoped() -> None:
    async def case(alice, bob):
        events: asyncio.Queue[dict] = asyncio.Queue()

        @bob.on("typing:changed")
        async def changed(payload: dict) -> None:
            await events.put(payload)

        await alice.emit("typing:set", {"data": {"room_id": "general", "is_typing": True}})
        payload = await asyncio.wait_for(events.get(), timeout=2)
        assert payload["data"]["username"] == "alice"
        assert payload["data"]["is_typing"] is True

    asyncio.run(event_case(case))


def test_delivery_and_read_status_events() -> None:
    async def case(alice, bob):
        delivered: asyncio.Queue[dict] = asyncio.Queue()
        read: asyncio.Queue[dict] = asyncio.Queue()

        @bob.on("message:status")
        async def bob_status(payload: dict) -> None:
            if payload.get("data", {}).get("status") == "delivered":
                await delivered.put(payload)

        @alice.on("message:status")
        async def alice_status(payload: dict) -> None:
            if payload.get("data", {}).get("status") == "read":
                await read.put(payload)

        message = {"room_id": "general", "client_message_id": "status-1", "kind": "text", "text": "status check"}
        await alice.emit("message:send", {"data": message, "request_id": "status-1"})
        delivery = await asyncio.wait_for(delivered.get(), timeout=2)
        assert delivery["data"]["status"] == "delivered"
        await bob.emit("message:read", {"data": {"room_id": "general", "message_id": delivery["data"]["message_id"]}})
        receipt = await asyncio.wait_for(read.get(), timeout=2)
        assert receipt["data"]["status"] == "read"
        assert receipt["data"]["user_id"] is not None

    asyncio.run(event_case(case))


def test_presence_online_and_offline_events() -> None:
    async def case(alice, bob):
        events: asyncio.Queue[dict] = asyncio.Queue()

        @alice.on("presence:changed")
        async def changed(payload: dict) -> None:
            await events.put(payload)

        await bob.emit("room:join", {"data": {"room_id": "general"}})
        online = await asyncio.wait_for(events.get(), timeout=2)
        assert online["data"]["online"] is True
        await bob.disconnect()
        offline = await asyncio.wait_for(events.get(), timeout=2)
        assert offline["data"]["online"] is False

    asyncio.run(event_case(case))
