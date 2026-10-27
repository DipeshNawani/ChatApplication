import asyncio
import random
from concurrent.futures import Future
from typing import Any, Coroutine

import socketio
import aiohttp
from PyQt6.QtCore import QThread, pyqtSignal


class SocketWorker(QThread):
    connection_state_changed = pyqtSignal(str)
    message_received = pyqtSignal(dict)
    message_acknowledged = pyqtSignal(dict)
    server_error = pyqtSignal(dict)
    history_received = pyqtSignal(dict)
    authentication_failed = pyqtSignal(str)
    room_added = pyqtSignal(dict)
    room_removed = pyqtSignal(dict)
    typing_received = pyqtSignal(dict)
    presence_changed = pyqtSignal(dict)
    status_changed = pyqtSignal(dict)

    def __init__(self, server_url: str, username: str, token: str = "") -> None:
        super().__init__()
        self.server_url = server_url.rstrip("/")
        self.username = username
        self.token = token
        self._stop_requested = False
        self._loop: asyncio.AbstractEventLoop | None = None
        self._client: socketio.AsyncClient | None = None
        self._active_rooms: set[str] = set()
        self._joined_rooms: set[str] = set()
        self._last_sequence_by_room: dict[str, int] = {}
        self._pending_messages: dict[str, dict[str, Any]] = {}
        self._disconnect_event: asyncio.Event | None = None
        self._wake_event: asyncio.Event | None = None

    def run(self) -> None:
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)
        try:
            self._loop.run_until_complete(self._connection_loop())
        finally:
            self._loop.close()
            self._loop = None

    def stop(self) -> None:
        self._stop_requested = True
        if self._loop and self._loop.is_running():
            self._submit(self._request_stop())

    def join_room(self, room_id: str) -> None:
        room_id = room_id.strip()
        if not room_id:
            return
        self._active_rooms.add(room_id)
        self._submit(self._join_room(room_id))

    def send_message(self, room_id: str, client_message_id: str, text: str, kind: str = "text", file_id: str | None = None) -> None:
        self._submit(self._queue_message(room_id, client_message_id, text, kind, file_id))

    def set_typing(self, room_id: str, is_typing: bool) -> None:
        self._submit(self._set_typing(room_id, is_typing))

    def mark_read(self, room_id: str, message_id: str) -> None:
        self._submit(self._mark_read(room_id, message_id))

    def _submit(self, coroutine: Coroutine[Any, Any, Any]) -> Future[Any] | None:
        if not self._loop:
            coroutine.close()
            return None
        return asyncio.run_coroutine_threadsafe(coroutine, self._loop)

    async def _connection_loop(self) -> None:
        client = socketio.AsyncClient(reconnection=False, request_timeout=5)
        self._client = client
        disconnect_event = asyncio.Event()
        self._disconnect_event = disconnect_event
        self._wake_event = asyncio.Event()

        @client.on("message:created")
        async def on_message(payload: dict[str, Any]) -> None:
            data = payload.get("data", {})
            if isinstance(data.get("sequence_id"), int) and isinstance(data.get("room_id"), str):
                self._last_sequence_by_room[data["room_id"]] = max(self._last_sequence_by_room.get(data["room_id"], 0), data["sequence_id"])
            client_message_id = data.get("client_message_id")
            if client_message_id:
                pending = self._pending_messages.pop(client_message_id, None)
                if pending is not None:
                    pending["message_id"] = data.get("message_id")
            self.message_received.emit(payload)

        @client.on("room:joined")
        async def on_room_joined(payload: dict[str, Any]) -> None:
            room_id = payload.get("data", {}).get("room_id")
            if not room_id:
                return
            self._joined_rooms.add(room_id)
            await self._load_history(room_id)
            for message in list(self._pending_messages.values()):
                if message["payload"]["data"]["room_id"] == room_id and client.connected:
                    await client.emit("message:send", message["payload"])

        @client.on("room:added")
        async def on_room_added(payload: dict[str, Any]) -> None:
            self.room_added.emit(payload)

        @client.on("room:removed")
        async def on_room_removed(payload: dict[str, Any]) -> None:
            self.room_removed.emit(payload)

        @client.on("typing:changed")
        async def on_typing(payload: dict[str, Any]) -> None:
            self.typing_received.emit(payload)

        @client.on("presence:changed")
        async def on_presence(payload: dict[str, Any]) -> None:
            self.presence_changed.emit(payload)

        @client.on("message:status")
        async def on_status(payload: dict[str, Any]) -> None:
            self.status_changed.emit(payload)

        @client.on("message:ack")
        async def on_ack(payload: dict[str, Any]) -> None:
            self.message_acknowledged.emit(payload)
            data = payload.get("data", {})
            request_id = payload.get("request_id")
            if data.get("status") == "sent" and data.get("message_id"):
                self._pending_messages = {
                    key: value
                    for key, value in self._pending_messages.items()
                    if value.get("message_id") != data["message_id"]
                }
                if request_id:
                    self._pending_messages.pop(request_id, None)
            elif data.get("code") in {"RATE_LIMITED", "NOT_IN_ROOM", "INVALID_MESSAGE"} and request_id:
                self._pending_messages.pop(request_id, None)

        @client.on("server:error")
        async def on_server_error(payload: dict[str, Any]) -> None:
            self.server_error.emit(payload)

        @client.event
        async def disconnect(reason: str) -> None:
            del reason
            disconnect_event.set()

        @client.event
        async def connect_error(data: Any) -> None:
            code = data.get("code") if isinstance(data, dict) else str(data)
            if code == "TOKEN_EXPIRED" or "TOKEN_EXPIRED" in str(data):
                self.authentication_failed.emit("TOKEN_EXPIRED")
                self._stop_requested = True

        attempt = 0
        while not self._stop_requested:
            self.connection_state_changed.emit("Connecting..." if attempt == 0 else f"Reconnecting (attempt {attempt})...")
            disconnect_event.clear()
            try:
                auth = {"token": self.token} if self.token else {"username": self.username}
                await client.connect(self.server_url, auth=auth, transports=["websocket", "polling"])
                attempt = 0
                self._joined_rooms.clear()
                self.connection_state_changed.emit("Connected")
                await self._restore_connection()
                await disconnect_event.wait()
            except Exception as error:
                self.server_error.emit({"data": {"code": "CONNECTION_ERROR", "message": str(error)}})
            finally:
                if client.connected:
                    await client.disconnect()

            if self._stop_requested:
                break
            attempt += 1
            self.connection_state_changed.emit("Offline")
            delay = min(30, 2 ** min(attempt, 5)) + random.uniform(0, 0.5)
            if self._wake_event:
                self._wake_event.clear()
                try:
                    await asyncio.wait_for(self._wake_event.wait(), timeout=delay)
                except asyncio.TimeoutError:
                    pass

        self.connection_state_changed.emit("Offline")

    async def _load_history(self, room_id: str) -> None:
        if not self.token:
            return
        params = {"limit": "50"}
        if room_id in self._last_sequence_by_room:
            params["after"] = str(self._last_sequence_by_room[room_id])
        try:
            async with aiohttp.ClientSession() as session:
                while True:
                    async with session.get(
                        f"{self.server_url}/api/v1/rooms/{room_id}/messages",
                        params=params,
                        headers={"Authorization": f"Bearer {self.token}"},
                        timeout=5,
                    ) as response:
                        if response.status == 401:
                            self.authentication_failed.emit("TOKEN_EXPIRED")
                            self._stop_requested = True
                            return
                        payload = await response.json()
                        if response.status >= 400:
                            self.server_error.emit({"data": payload.get("error", {"code": "HISTORY_ERROR", "message": "History request failed"})})
                            return
                        self.history_received.emit({"room_id": room_id, **payload})
                        sequences = [message.get("sequence_id") for message in payload.get("messages", []) if isinstance(message.get("sequence_id"), int)]
                        if sequences:
                            self._last_sequence_by_room[room_id] = max(self._last_sequence_by_room.get(room_id, 0), max(sequences))
                        if not payload.get("has_more"):
                            return
                        params["after"] = str(self._last_sequence_by_room[room_id])
        except Exception as error:
            self.server_error.emit({"data": {"code": "HISTORY_ERROR", "message": str(error)}})

    async def _restore_connection(self) -> None:
        if not self._client:
            return
        for room_id in list(self._active_rooms):
            await self._client.emit("room:join", {"data": {"room_id": room_id}})
        for message in list(self._pending_messages.values()):
            room_id = message["payload"]["data"]["room_id"]
            if room_id in self._joined_rooms:
                await self._client.emit("message:send", message["payload"])

    async def _join_room(self, room_id: str) -> None:
        if self._client and self._client.connected:
            await self._client.emit("room:join", {"data": {"room_id": room_id}})

    async def _queue_message(self, room_id: str, client_message_id: str, text: str, kind: str, file_id: str | None) -> None:
        payload = {
            "request_id": client_message_id,
            "data": {
                "room_id": room_id,
                "client_message_id": client_message_id,
                "kind": kind,
                "text": text,
                "file_id": file_id,
            },
        }
        self._pending_messages[client_message_id] = {"payload": payload}
        if self._client and self._client.connected and room_id in self._joined_rooms:
            await self._client.emit("message:send", payload)

    async def _set_typing(self, room_id: str, is_typing: bool) -> None:
        if self._client and self._client.connected and room_id in self._joined_rooms:
            await self._client.emit("typing:set", {"data": {"room_id": room_id, "is_typing": is_typing}})

    async def _mark_read(self, room_id: str, message_id: str) -> None:
        if self._client and self._client.connected and room_id in self._joined_rooms:
            await self._client.emit("message:read", {"data": {"room_id": room_id, "message_id": message_id}})

    async def _request_stop(self) -> None:
        if self._wake_event:
            self._wake_event.set()
        if self._client and self._client.connected:
            await self._client.disconnect()
        if self._disconnect_event:
            self._disconnect_event.set()