import asyncio
import socket
import sys
import tempfile
import time
from pathlib import Path

import aiohttp
import pytest
import socketio
import uvicorn

sys.path.insert(0, str(Path(__file__).parents[1]))

from app import auth, main, routes  # noqa: E402
from app.database import configure_database, create_user, dispose_database, init_database  # noqa: E402
from app.rate_limit import PerUserRateLimiter  # noqa: E402

SECRET = "group-socket-tests-secret-0123456789"


def wait_for_port(port: int, timeout: float = 6) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.2):
                return
        except OSError:
            time.sleep(0.05)
    raise TimeoutError(f"port {port} did not open")


def test_group_add_and_remove_evicts_socket_and_emits_events(tmp_path, monkeypatch) -> None:
    async def case() -> None:
        monkeypatch.setattr(main, "DEV_MODE", False)
        monkeypatch.setattr(main, "JWT_SECRET", SECRET)
        monkeypatch.setattr(auth, "JWT_SECRET", SECRET)
        monkeypatch.setattr(routes, "auth_rate_limiter", PerUserRateLimiter())
        configure_database(str(tmp_path / "room-events.db"))
        init_database(create_schema=True)
        owner = create_user("owner", auth.hash_password("password-123"))
        invited = create_user("invited", auth.hash_password("password-123"))
        owner_token = auth.create_access_token(owner)
        invited_token = auth.create_access_token(invited)
        server = uvicorn.Server(uvicorn.Config(main.socket_app, host="127.0.0.1", port=8768, log_level="error"))
        server_task = asyncio.create_task(server.serve())
        await asyncio.to_thread(wait_for_port, 8768)
        client = socketio.AsyncClient(reconnection=False)
        added_events: asyncio.Queue[dict] = asyncio.Queue()
        removed_events: asyncio.Queue[dict] = asyncio.Queue()
        joined_events: asyncio.Queue[dict] = asyncio.Queue()

        @client.on("room:added")
        async def on_added(payload: dict) -> None:
            await added_events.put(payload)

        @client.on("room:removed")
        async def on_removed(payload: dict) -> None:
            await removed_events.put(payload)

        @client.on("room:joined")
        async def on_joined(payload: dict) -> None:
            await joined_events.put(payload)

        try:
            await client.connect("http://127.0.0.1:8768", auth={"token": invited_token})
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    "http://127.0.0.1:8768/api/v1/rooms/groups",
                    json={"name": "Socket Group"},
                    headers={"Authorization": f"Bearer {owner_token}"},
                ) as response:
                    room_id = (await response.json())["room"]["room_id"]
                async with session.post(
                    f"http://127.0.0.1:8768/api/v1/rooms/{room_id}/members",
                    json={"username": "invited"},
                    headers={"Authorization": f"Bearer {owner_token}"},
                ) as response:
                    assert response.status == 200
            added = await asyncio.wait_for(added_events.get(), timeout=2)
            assert added["data"]["room_id"] == room_id
            await client.emit("room:join", {"data": {"room_id": room_id}})
            assert (await asyncio.wait_for(joined_events.get(), timeout=2))["data"]["room_id"] == room_id
            async with aiohttp.ClientSession() as session:
                async with session.delete(
                    f"http://127.0.0.1:8768/api/v1/rooms/{room_id}/members/invited",
                    headers={"Authorization": f"Bearer {owner_token}"},
                ) as response:
                    assert response.status == 200
            removed = await asyncio.wait_for(removed_events.get(), timeout=2)
            assert removed["data"]["room_id"] == room_id
            assert room_id not in main.joined_rooms.get(next(iter(main.connected_users.keys())), set())
        finally:
            await client.disconnect()
            server.should_exit = True
            await server_task
            dispose_database()

    asyncio.run(case())
