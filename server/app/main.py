from datetime import datetime, timezone
import secrets
from contextlib import asynccontextmanager
from typing import Any

import jwt
import socketio
from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.middleware.cors import CORSMiddleware

from .auth import create_access_token, decode_token, hash_password
from .config import CORS_ORIGINS, DEV_MODE, GENERAL_ROOM_ID, JWT_SECRET, MAX_MESSAGE_LENGTH, MAX_ROOM_ID_LENGTH, PROTOCOL_VERSION
from .database import (
    create_user,
    get_user_by_id,
    get_user_by_username,
    get_file,
    message_belongs_to_room,
    init_database,
    is_member,
    save_message,
)
from .rate_limit import Limit, PerUserRateLimiter
from .routes import router


@asynccontextmanager
async def lifespan(application: FastAPI):
    del application
    if len(JWT_SECRET) < 32:
        raise RuntimeError("JWT_SECRET must be at least 32 characters")
    if "*" in CORS_ORIGINS:
        raise RuntimeError("CORS_ORIGINS must not contain wildcard origins")
    init_database()
    yield


app = FastAPI(title="QuantumBytes Chat Server", version="0.2.0", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=CORS_ORIGINS, allow_methods=["GET", "POST", "DELETE"], allow_headers=["Authorization", "Content-Type"], allow_credentials=False)
app.include_router(router)
sio = socketio.AsyncServer(async_mode="asgi", cors_allowed_origins=CORS_ORIGINS)
socket_app = socketio.ASGIApp(sio, other_asgi_app=app)
rate_limiter = PerUserRateLimiter()
connected_users: dict[str, int] = {}
joined_rooms: dict[str, set[str]] = {}
app.state.sio = sio
app.state.connected_users = connected_users
app.state.joined_rooms = joined_rooms


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exception: HTTPException) -> JSONResponse:
    del request
    detail = exception.detail if isinstance(exception.detail, dict) else {"message": str(exception.detail)}
    return JSONResponse(status_code=exception.status_code, content={"error": {"code": detail.get("code", "HTTP_ERROR"), "message": detail.get("message", "Request failed")}})


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exception: RequestValidationError) -> JSONResponse:
    del request
    del exception
    return JSONResponse(status_code=422, content={"error": {"code": "VALIDATION_ERROR", "message": "Request validation failed"}})


def envelope(data: dict[str, Any], request_id: str | None = None) -> dict[str, Any]:
    payload: dict[str, Any] = {"protocol_version": PROTOCOL_VERSION, "data": data}
    if request_id:
        payload["request_id"] = request_id
    return payload


def error_payload(code: str, message: str, request_id: str | None = None, **extra: Any) -> dict[str, Any]:
    return envelope({"code": code, "message": message, **extra}, request_id)


def occurred_at() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def get_request(data: Any) -> tuple[str | None, dict[str, Any]]:
    if not isinstance(data, dict):
        return None, {}
    request_id = data.get("request_id")
    payload = data.get("data", data)
    return request_id if isinstance(request_id, str) else None, payload if isinstance(payload, dict) else {}


def user_for_sid(sid: str):
    user_id = connected_users.get(sid)
    return get_user_by_id(user_id) if user_id else None


@app.get("/health")
async def health() -> dict[str, str | bool]:
    return {"status": "ok", "dev_mode": DEV_MODE}


async def authenticate_socket(sid: str, auth: Any) -> bool:
    user = None
    if DEV_MODE and isinstance(auth, dict) and isinstance(auth.get("username"), str):
        username = auth["username"].strip().lower()
        user = get_user_by_username(username)
        if user is None:
            user = create_user(username, hash_password(secrets.token_urlsafe(32)))
    elif isinstance(auth, dict) and isinstance(auth.get("token"), str):
        try:
            payload = decode_token(auth["token"])
            user = get_user_by_id(int(payload["sub"]))
        except (jwt.PyJWTError, KeyError, TypeError, ValueError):
            raise ConnectionRefusedError({"code": "TOKEN_EXPIRED", "message": "Login has expired"})
    if user is None:
        raise ConnectionRefusedError({"code": "AUTH_REQUIRED", "message": "Valid authentication is required"})
    connected_users[sid] = user.id
    joined_rooms[sid] = set()
    if is_member(GENERAL_ROOM_ID, user.id):
        await sio.enter_room(sid, GENERAL_ROOM_ID)
        joined_rooms[sid].add(GENERAL_ROOM_ID)
        await sio.emit("presence:changed", {**envelope({"room_id": GENERAL_ROOM_ID, "user_id": user.id, "username": user.username, "online": True}), "occurred_at": occurred_at()}, room=GENERAL_ROOM_ID, skip_sid=sid)
    await sio.emit("connection:state", envelope({"state": "connected", "username": user.username}), to=sid)
    return True


@sio.event
async def connect(sid: str, environ: dict[str, Any], auth: Any) -> bool:
    del environ
    try:
        return await authenticate_socket(sid, auth)
    except ConnectionRefusedError:
        raise


@sio.event
async def disconnect(sid: str) -> None:
    user = user_for_sid(sid)
    if user:
        for room_id in list(joined_rooms.get(sid, set())):
            await sio.emit("presence:changed", {**envelope({"room_id": room_id, "user_id": user.id, "username": user.username, "online": False}), "occurred_at": occurred_at()}, room=room_id, skip_sid=sid)
    connected_users.pop(sid, None)
    joined_rooms.pop(sid, None)


@sio.on("session:authenticate")
async def session_authenticate(sid: str, data: Any) -> None:
    request_id, payload = get_request(data)
    token = payload.get("token")
    try:
        if DEV_MODE and isinstance(payload.get("username"), str):
            await authenticate_socket(sid, {"username": payload["username"]})
        elif isinstance(token, str):
            await authenticate_socket(sid, {"token": token})
        else:
            raise ConnectionRefusedError({"code": "AUTH_REQUIRED", "message": "Valid authentication is required"})
        user = user_for_sid(sid)
        await sio.emit("connection:state", envelope({"state": "authenticated", "username": user.username}, request_id), to=sid)
    except ConnectionRefusedError as error:
        await sio.emit("server:error", error_payload(*error.args[0].values(), request_id=request_id), to=sid)


@sio.on("room:join")
async def room_join(sid: str, data: Any) -> None:
    request_id, payload = get_request(data)
    user = user_for_sid(sid)
    room_id = payload.get("room_id")
    if not user or not isinstance(room_id, str) or not room_id.strip() or len(room_id.strip()) > MAX_ROOM_ID_LENGTH:
        await sio.emit("server:error", error_payload("INVALID_ROOM", "room_id is required", request_id), to=sid)
        return
    normalized_room_id = room_id.strip()
    if not is_member(normalized_room_id, user.id):
        await sio.emit("server:error", error_payload("NOT_IN_ROOM", "You are not a member of this room", request_id), to=sid)
        return
    await sio.enter_room(sid, normalized_room_id)
    joined_rooms.setdefault(sid, set()).add(normalized_room_id)
    await sio.emit("room:joined", envelope({"room_id": normalized_room_id}, request_id), to=sid)
    await sio.emit("presence:changed", {**envelope({"room_id": normalized_room_id, "user_id": user.id, "username": user.username, "online": True}), "occurred_at": occurred_at()}, room=normalized_room_id, skip_sid=sid)


@sio.on("room:leave")
async def room_leave(sid: str, data: Any) -> None:
    request_id, payload = get_request(data)
    room_id = payload.get("room_id")
    if isinstance(room_id, str) and room_id.strip():
        normalized_room_id = room_id.strip()
        await sio.leave_room(sid, normalized_room_id)
        joined_rooms.setdefault(sid, set()).discard(normalized_room_id)
        await sio.emit("room:left", envelope({"room_id": normalized_room_id}, request_id), to=sid)


@sio.on("message:send")
async def message_send(sid: str, data: Any) -> None:
    request_id, payload = get_request(data)
    user = user_for_sid(sid)
    room_id = payload.get("room_id")
    client_message_id = payload.get("client_message_id")
    text = payload.get("text", "")
    kind = payload.get("kind", "text")
    file_id = payload.get("file_id")
    if not user or not isinstance(room_id, str) or not room_id.strip() or len(room_id.strip()) > MAX_ROOM_ID_LENGTH:
        await sio.emit("message:ack", error_payload("INVALID_MESSAGE", "room_id is required", request_id), to=sid)
        return
    normalized_room_id = room_id.strip()
    if not is_member(normalized_room_id, user.id) or normalized_room_id not in joined_rooms.get(sid, set()):
        await sio.emit("message:ack", error_payload("NOT_IN_ROOM", "You are not a member of this room", request_id), to=sid)
        return
    if not isinstance(client_message_id, str) or not client_message_id.strip():
        await sio.emit("message:ack", error_payload("INVALID_MESSAGE", "Message text and client_message_id are required", request_id), to=sid)
        return
    if not isinstance(text, str):
        await sio.emit("message:ack", error_payload("INVALID_MESSAGE", "text must be a string", request_id), to=sid)
        return
    if kind == "text" and not text.strip():
        await sio.emit("message:ack", error_payload("INVALID_MESSAGE", "Message text and client_message_id are required", request_id), to=sid)
        return
    file_metadata = get_file(file_id) if isinstance(file_id, str) else None
    if kind in {"file", "image"} and (file_metadata is None or file_metadata.owner_user_id != user.id):
        await sio.emit("message:ack", error_payload("INVALID_MESSAGE", "A valid file_id is required", request_id), to=sid)
        return
    if kind not in {"text", "file", "image"}:
        await sio.emit("message:ack", error_payload("INVALID_MESSAGE", "Unsupported message kind", request_id), to=sid)
        return
    if len(text.strip()) > MAX_MESSAGE_LENGTH:
        await sio.emit("message:ack", error_payload("MESSAGE_TOO_LONG", "Message exceeds the maximum length", request_id), to=sid)
        return
    allowed, retry_after = rate_limiter.allow(str(user.id), "message:send", Limit(10, 10))
    if not allowed:
        await sio.emit("message:ack", error_payload("RATE_LIMITED", "Too many messages", request_id, retry_after_seconds=retry_after), to=sid)
        return
    message = save_message(normalized_room_id, user.id, client_message_id.strip(), kind, text.strip(), file_id)
    if not message["created"]:
        await sio.emit("message:ack", envelope({"message_id": message["message_id"], "status": "sent", "duplicate": True}, request_id), to=sid)
        return
    message_data = {
        "sequence_id": message["sequence_id"],
        "message_id": message["message_id"],
        "client_message_id": message["client_message_id"],
        "room_id": message["room_id"],
        "sender": {"user_id": user.id, "username": user.username},
        "kind": message["kind"],
        "text": message["text"],
        "file": None,
        "status": "sent",
    }
    if file_metadata:
        message_data["file"] = {
            "file_id": file_metadata.id,
            "name": file_metadata.original_name,
            "content_type": file_metadata.content_type,
            "size": file_metadata.size,
        }
    await sio.emit("message:created", {**envelope(message_data, request_id), "occurred_at": message["occurred_at"]}, room=normalized_room_id)
    await sio.emit("message:ack", envelope({"message_id": message["message_id"], "status": "sent"}, request_id), to=sid)
    await sio.emit("message:status", envelope({"message_id": message["message_id"], "room_id": normalized_room_id, "status": "delivered"}), room=normalized_room_id, skip_sid=sid)


@sio.on("typing:set")
async def typing_set(sid: str, data: Any) -> None:
    request_id, payload = get_request(data)
    user = user_for_sid(sid)
    room_id = payload.get("room_id")
    is_typing = payload.get("is_typing")
    if not user or not isinstance(room_id, str) or not room_id.strip() or len(room_id.strip()) > MAX_ROOM_ID_LENGTH or not isinstance(is_typing, bool):
        await sio.emit("server:error", error_payload("INVALID_TYPING", "room_id and is_typing are required", request_id), to=sid)
        return
    normalized_room_id = room_id.strip()
    if not is_member(normalized_room_id, user.id) or normalized_room_id not in joined_rooms.get(sid, set()):
        await sio.emit("server:error", error_payload("NOT_IN_ROOM", "You are not a member of this room", request_id), to=sid)
        return
    allowed, retry_after = rate_limiter.allow(str(user.id), "typing:set", Limit(30, 10))
    if not allowed:
        await sio.emit("server:error", error_payload("RATE_LIMITED", "Too many typing events", request_id, retry_after_seconds=retry_after), to=sid)
        return
    await sio.emit("typing:changed", {**envelope({"room_id": normalized_room_id, "username": user.username, "is_typing": is_typing}, request_id), "occurred_at": occurred_at()}, room=normalized_room_id, skip_sid=sid)


@sio.on("message:read")
async def message_read(sid: str, data: Any) -> None:
    request_id, payload = get_request(data)
    user = user_for_sid(sid)
    room_id = payload.get("room_id")
    message_id = payload.get("message_id")
    if not user or not isinstance(room_id, str) or not isinstance(message_id, str) or not is_member(room_id, user.id) or not message_belongs_to_room(message_id, room_id):
        await sio.emit("server:error", error_payload("NOT_IN_ROOM", "You are not a member of this room", request_id), to=sid)
        return
    await sio.emit("message:status", envelope({"message_id": message_id, "room_id": room_id, "status": "read", "user_id": user.id}, request_id), room=room_id)
