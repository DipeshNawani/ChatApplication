import asyncio
import socket
import sys
import tempfile
import time
from pathlib import Path
from typing import Any, Awaitable, Callable

import aiohttp
import pytest
import socketio
import uvicorn

sys.path.insert(0, str(Path(__file__).parents[1]))

from app import auth, main  # noqa: E402
from app.database import configure_database, create_user, dispose_database, get_user_by_username, init_database  # noqa: E402


SECRET = "phase2-test-secret-0123456789abcdef"


def unused_port() -> int:
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        return int(listener.getsockname()[1])


async def wait_for_port(port: int, timeout: float = 5) -> None:
    deadline = time.monotonic() + timeout
    async with aiohttp.ClientSession() as session:
        while time.monotonic() < deadline:
            try:
                async with session.get(f"http://127.0.0.1:{port}/health", timeout=0.2) as response:
                    if response.status == 200 and (await response.json()).get("status") == "ok":
                        return
            except (aiohttp.ClientError, asyncio.TimeoutError):
                pass
            await asyncio.sleep(0.05)
    raise TimeoutError(f"port {port} did not open")


async def room_case(callback: Callable[[socketio.AsyncClient, socketio.AsyncClient, asyncio.Queue, asyncio.Queue, asyncio.Queue], Awaitable[None]]) -> None:
    with tempfile.TemporaryDirectory() as temporary_directory:
        main.DEV_MODE = True
        main.JWT_SECRET = SECRET
        configure_database(str(Path(temporary_directory) / "socket.db"))
        init_database(create_schema=True)
        port = unused_port()
        server = uvicorn.Server(uvicorn.Config(main.socket_app, host="127.0.0.1", port=port, log_level="error"))
        server_task = asyncio.create_task(server.serve())
        await wait_for_port(port)
        alice = socketio.AsyncClient(reconnection=False)
        bob = socketio.AsyncClient(reconnection=False)
        acks: asyncio.Queue[dict] = asyncio.Queue()
        messages: asyncio.Queue[dict] = asyncio.Queue()
        errors: asyncio.Queue[dict] = asyncio.Queue()

        @alice.on("message:ack")
        async def on_ack(payload: dict) -> None:
            await acks.put(payload)

        @bob.on("message:created")
        async def on_message(payload: dict) -> None:
            await messages.put(payload)

        @alice.on("server:error")
        async def on_error(payload: dict) -> None:
            await errors.put(payload)

        try:
            await alice.connect(f"http://127.0.0.1:{port}", auth={"username": "alice"})
            await bob.connect(f"http://127.0.0.1:{port}", auth={"username": "bob"})
            await alice.emit("room:join", {"data": {"room_id": "general"}})
            await bob.emit("room:join", {"data": {"room_id": "general"}})
            await asyncio.sleep(0.1)
            await callback(alice, bob, acks, messages, errors)
        finally:
            await alice.disconnect()
            await bob.disconnect()
            server.should_exit = True
            await server_task
            dispose_database()


def test_duplicate_retry_sends_only_ack() -> None:
    async def case(alice, bob, acks, messages, errors):
        payload = {"data": {"room_id": "general", "client_message_id": "duplicate", "kind": "text", "text": "hello"}}
        await alice.emit("message:send", payload)
        first_message = await asyncio.wait_for(messages.get(), timeout=2)
        await asyncio.wait_for(acks.get(), timeout=2)
        await alice.emit("message:send", payload)
        duplicate_ack = await asyncio.wait_for(acks.get(), timeout=2)
        assert duplicate_ack["data"] == {"message_id": first_message["data"]["message_id"], "status": "sent", "duplicate": True}
        assert messages.empty()

    asyncio.run(room_case(case))


def test_message_send_not_in_room() -> None:
    async def case(alice, bob, acks, messages, errors):
        await alice.emit("message:send", {"data": {"room_id": "missing-room", "client_message_id": "not-member", "kind": "text", "text": "nope"}})
        assert (await asyncio.wait_for(acks.get(), timeout=2))["data"]["code"] == "NOT_IN_ROOM"

    asyncio.run(room_case(case))


def test_typing_not_in_room() -> None:
    async def case(alice, bob, acks, messages, errors):
        await alice.emit("typing:set", {"data": {"room_id": "missing-room", "is_typing": True}})
        assert (await asyncio.wait_for(errors.get(), timeout=2))["data"]["code"] == "NOT_IN_ROOM"

    asyncio.run(room_case(case))


def test_eleventh_message_is_rate_limited() -> None:
    async def case(alice, bob, acks, messages, errors):
        for index in range(11):
            await alice.emit("message:send", {"data": {"room_id": "general", "client_message_id": f"rate-{index}", "kind": "text", "text": str(index)}})
        results = [(await asyncio.wait_for(acks.get(), timeout=2))["data"] for _ in range(11)]
        assert any(result.get("code") == "RATE_LIMITED" for result in results)

    asyncio.run(room_case(case))


def test_empty_message_is_rejected() -> None:
    async def case(alice, bob, acks, messages, errors):
        await alice.emit("message:send", {"data": {"room_id": "general", "client_message_id": "empty", "kind": "text", "text": " "}})
        assert (await asyncio.wait_for(acks.get(), timeout=2))["data"]["code"] == "INVALID_MESSAGE"

    asyncio.run(room_case(case))


def test_4001_character_message_is_rejected() -> None:
    async def case(alice, bob, acks, messages, errors):
        await alice.emit("message:send", {"data": {"room_id": "general", "client_message_id": "long", "kind": "text", "text": "x" * 4001}})
        assert (await asyncio.wait_for(acks.get(), timeout=2))["data"]["code"] == "MESSAGE_TOO_LONG"

    asyncio.run(room_case(case))


def test_username_auth_is_refused_when_dev_mode_is_off() -> None:
    async def case() -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            main.DEV_MODE = False
            main.JWT_SECRET = SECRET
            configure_database(str(Path(temporary_directory) / "auth.db"))
            init_database(create_schema=True)
            port = unused_port()
            server = uvicorn.Server(uvicorn.Config(main.socket_app, host="127.0.0.1", port=port, log_level="error"))
            server_task = asyncio.create_task(server.serve())
            await wait_for_port(port)
            client = socketio.AsyncClient(reconnection=False)
            try:
                with pytest.raises(socketio.exceptions.ConnectionError):
                    await client.connect(f"http://127.0.0.1:{port}", auth={"username": "alice"})
            finally:
                await client.disconnect()
                server.should_exit = True
                await server_task
                dispose_database()

    asyncio.run(case())


def test_room_added_is_sent_to_other_direct_chat_user() -> None:
    async def case() -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            main.DEV_MODE = False
            main.JWT_SECRET = SECRET
            auth.JWT_SECRET = SECRET
            configure_database(str(Path(temporary_directory) / "direct.db"))
            init_database(create_schema=True)
            alice = create_user("alice", auth.hash_password("password-123"))
            bob = create_user("bob", auth.hash_password("password-123"))
            alice_token = auth.create_access_token(alice)
            bob_token = auth.create_access_token(bob)
            port = unused_port()
            server = uvicorn.Server(uvicorn.Config(main.socket_app, host="127.0.0.1", port=port, log_level="error"))
            server_task = asyncio.create_task(server.serve())
            await wait_for_port(port)
            bob_client = socketio.AsyncClient(reconnection=False)
            added: asyncio.Queue[dict] = asyncio.Queue()

            @bob_client.on("room:added")
            async def on_added(payload: dict) -> None:
                await added.put(payload)

            try:
                await bob_client.connect(f"http://127.0.0.1:{port}", auth={"token": bob_token})
                async with aiohttp.ClientSession() as session:
                    async with session.post(
                        f"http://127.0.0.1:{port}/api/v1/chats/direct",
                        json={"username": "bob"},
                        headers={"Authorization": f"Bearer {alice_token}"},
                    ) as response:
                        assert response.status == 200
                event = await asyncio.wait_for(added.get(), timeout=2)
                assert event["data"]["name"] == "alice"
                assert event["data"]["kind"] == "direct"
            finally:
                await bob_client.disconnect()
                server.should_exit = True
                await server_task
                dispose_database()

    asyncio.run(case())
