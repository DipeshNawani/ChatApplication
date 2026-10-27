from pathlib import Path
from uuid import uuid4
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, File, HTTPException, Query, Request, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlalchemy.exc import IntegrityError

from .auth import bearer_user, create_access_token, hash_password, verify_password
from .config import ALLOWED_FILE_EXTENSIONS, MAX_FILE_SIZE, MAX_GROUP_MEMBERS, TRUST_PROXY_HEADERS, UPLOAD_DIRECTORY
from .database import FileObject, Membership, Message, User, add_member, create_group_room, create_user, get_file, get_history, get_or_create_direct_room, get_room, get_user_by_username, is_member, list_rooms, remove_member, search_users
from .rate_limit import Limit, PerUserRateLimiter

router = APIRouter(prefix="/api/v1")
auth_rate_limiter = PerUserRateLimiter()
dummy_password_hash = hash_password("phase4-dummy-password-value")


def rate_limit_source(request: Request) -> str:
    if TRUST_PROXY_HEADERS:
        forwarded_for = request.headers.get("x-forwarded-for", "").split(",", 1)[0].strip()
        if forwarded_for:
            return forwarded_for[:64]
    return request.client.host if request.client else "unknown"


class Credentials(BaseModel):
    username: str = Field(min_length=3, max_length=32)
    password: str = Field(min_length=8, max_length=128)


class DirectChatRequest(BaseModel):
    username: str = Field(min_length=3, max_length=32)


class GroupRequest(BaseModel):
    name: str = Field(min_length=1, max_length=64)


class MemberRequest(BaseModel):
    username: str = Field(min_length=3, max_length=32)


def user_response(user: User, token: str) -> dict[str, object]:
    return {"access_token": token, "token_type": "bearer", "user": {"user_id": user.id, "username": user.username}}


@router.post("/auth/register", status_code=201)
def register(credentials: Credentials, request: Request) -> dict[str, object]:
    source = rate_limit_source(request)
    allowed, retry_after = auth_rate_limiter.allow(source, "register", Limit(5, 60))
    if not allowed:
        raise HTTPException(status_code=429, detail={"code": "RATE_LIMITED", "retry_after_seconds": retry_after})
    normalized = credentials.username.lower()
    from .config import RESERVED_USERNAMES, USERNAME_PATTERN
    if not USERNAME_PATTERN.fullmatch(credentials.username) or normalized in RESERVED_USERNAMES:
        raise HTTPException(status_code=400, detail={"code": "INVALID_USERNAME", "message": "Username is not available"})
    if get_user_by_username(normalized) is not None:
        raise HTTPException(status_code=409, detail={"code": "USERNAME_UNAVAILABLE", "message": "Username is not available"})
    try:
        user = create_user(normalized, hash_password(credentials.password))
    except IntegrityError as error:
        raise HTTPException(status_code=409, detail={"code": "USERNAME_UNAVAILABLE", "message": "Username is not available"}) from error
    return user_response(user, create_access_token(user))


@router.post("/auth/login")
def login(credentials: Credentials, request: Request) -> dict[str, object]:
    source = rate_limit_source(request)
    allowed, retry_after = auth_rate_limiter.allow(source, "login", Limit(10, 60))
    if not allowed:
        raise HTTPException(status_code=429, detail={"code": "RATE_LIMITED", "retry_after_seconds": retry_after})
    user = get_user_by_username(credentials.username.lower())
    stored_hash = user.password_hash if user is not None else dummy_password_hash
    valid_password = verify_password(credentials.password, stored_hash)
    if user is None or not valid_password:
        raise HTTPException(status_code=401, detail={"code": "INVALID_CREDENTIALS", "message": "Invalid username or password"})
    return user_response(user, create_access_token(user))


@router.get("/users/search")
async def users_search(q: str = Query(min_length=1, max_length=32), user: User = Depends(bearer_user)) -> dict[str, object]:
    return {"users": [{"user_id": item.id, "username": item.username} for item in search_users(q, user.id)]}


@router.get("/rooms")
async def rooms(user: User = Depends(bearer_user)) -> dict[str, object]:
    return {"rooms": list_rooms(user.id)}


@router.post("/chats/direct")
async def direct_chat(body: DirectChatRequest, request: Request, user: User = Depends(bearer_user)) -> dict[str, object]:
    other = get_user_by_username(body.username.lower())
    if other is None or other.id == user.id:
        raise HTTPException(status_code=404, detail={"code": "USER_NOT_FOUND", "message": "User not found"})
    room, created = get_or_create_direct_room(user.id, other.id)
    if created:
        for sid, connected_user_id in request.app.state.connected_users.items():
            if connected_user_id == other.id:
                await request.app.state.sio.emit(
                    "room:added",
                    {"protocol_version": 1, "data": {"room_id": room.id, "name": user.username, "kind": room.kind}},
                    to=sid,
                )
    return {"room": {"room_id": room.id, "name": other.username, "kind": room.kind}}


@router.post("/rooms/groups")
async def create_group(body: GroupRequest, request: Request, user: User = Depends(bearer_user)) -> dict[str, object]:
    normalized_name = body.name.strip()
    if not normalized_name:
        raise HTTPException(status_code=422, detail={"code": "INVALID_GROUP_NAME", "message": "Group name is required"})
    room = create_group_room(user.id, normalized_name)
    return {"room": {"room_id": room.id, "name": room.name, "kind": room.kind, "owner_id": user.id}}


@router.post("/rooms/{room_id}/members")
async def add_group_member(room_id: str, body: MemberRequest, request: Request, user: User = Depends(bearer_user)) -> dict[str, object]:
    other = get_user_by_username(body.username.lower())
    room = get_room(room_id)
    if other is None or room is None or room.kind != "group" or room.owner_id != user.id:
        raise HTTPException(status_code=403, detail={"code": "NOT_ALLOWED", "message": "You cannot add this member"})
    if not add_member(room_id, other.id, MAX_GROUP_MEMBERS):
        raise HTTPException(status_code=409, detail={"code": "MEMBER_LIMIT", "message": "Member could not be added"})
    for sid, connected_user_id in request.app.state.connected_users.items():
        if connected_user_id == other.id:
            await request.app.state.sio.emit("room:added", {"protocol_version": 1, "data": {"room_id": room_id, "name": room.name, "kind": "group"}}, to=sid)
    return {"ok": True}


@router.delete("/rooms/{room_id}/members/{username}")
async def remove_group_member(room_id: str, username: str, request: Request, user: User = Depends(bearer_user)) -> dict[str, object]:
    target = get_user_by_username(username.lower())
    if target is None:
        raise HTTPException(status_code=404, detail={"code": "USER_NOT_FOUND", "message": "User not found"})
    removed, new_owner_id, closed = remove_member(room_id, target.id, user.id)
    if not removed:
        raise HTTPException(status_code=403, detail={"code": "NOT_ALLOWED", "message": "You cannot remove this member"})
    for sid, connected_user_id in list(request.app.state.connected_users.items()):
        if connected_user_id == target.id:
            request.app.state.joined_rooms.get(sid, set()).discard(room_id)
            await request.app.state.sio.leave_room(sid, room_id)
            await request.app.state.sio.emit("room:removed", {"protocol_version": 1, "data": {"room_id": room_id, "closed": closed}}, to=sid)
    return {"ok": True, "closed": closed, "owner_id": new_owner_id}


@router.post("/rooms/{room_id}/leave")
async def leave_group(room_id: str, request: Request, user: User = Depends(bearer_user)) -> dict[str, object]:
    removed, new_owner_id, closed = remove_member(room_id, user.id, user.id)
    if not removed:
        raise HTTPException(status_code=403, detail={"code": "NOT_ALLOWED", "message": "You cannot leave this room"})
    for sid, connected_user_id in list(request.app.state.connected_users.items()):
        if connected_user_id == user.id:
            request.app.state.joined_rooms.get(sid, set()).discard(room_id)
            await request.app.state.sio.leave_room(sid, room_id)
            await request.app.state.sio.emit("room:removed", {"protocol_version": 1, "data": {"room_id": room_id, "closed": closed}}, to=sid)
    return {"ok": True, "closed": closed, "owner_id": new_owner_id}


@router.get("/rooms/{room_id}/messages")
async def history(
    room_id: str,
    limit: int = Query(default=50, ge=1, le=100),
    before: int | None = Query(default=None, ge=1),
    after: int | None = Query(default=None, ge=0),
    user: User = Depends(bearer_user),
) -> dict[str, object]:
    if before is not None and after is not None:
        raise HTTPException(status_code=400, detail={"code": "INVALID_CURSOR", "message": "Use before or after, not both"})
    if not is_member(room_id, user.id):
        raise HTTPException(status_code=403, detail={"code": "NOT_IN_ROOM", "message": "You are not a member of this room"})
    messages, has_more = get_history(room_id, user.id, limit, before, after)
    return {
        "messages": [
            {
                "sequence_id": message["sequence_id"],
                "message_id": message["message_id"],
                "room_id": message["room_id"],
                "sender": {"user_id": message["sender_user_id"], "username": message["sender_username"]},
                "client_message_id": message["client_message_id"],
                "kind": message["kind"],
                "text": message["text"],
                "occurred_at": message["occurred_at"],
                "status": "sent",
            }
            for message in messages
        ],
        "has_more": has_more,
        "next_before": messages[0]["sequence_id"] if messages and after is None else before,
        "next_after": messages[-1]["sequence_id"] if messages and after is not None else after,
    }


@router.post("/files")
def upload_file(file: UploadFile = File(...), user: User = Depends(bearer_user)) -> dict[str, object]:
    extension = Path(file.filename or "").suffix.lower()
    if extension not in ALLOWED_FILE_EXTENSIONS:
        raise HTTPException(status_code=415, detail={"code": "FILE_TYPE_NOT_ALLOWED", "message": "File type is not allowed"})
    content = file.file.read(MAX_FILE_SIZE + 1)
    if len(content) > MAX_FILE_SIZE:
        raise HTTPException(status_code=413, detail={"code": "FILE_TOO_LARGE", "message": "Maximum file size is 5 MB"})
    valid_content = {
        ".png": content.startswith(b"\x89PNG\r\n\x1a\n"),
        ".jpg": content.startswith(b"\xff\xd8\xff"),
        ".gif": content.startswith((b"GIF87a", b"GIF89a")),
        ".webp": len(content) >= 12 and content[:4] == b"RIFF" and content[8:12] == b"WEBP",
        ".pdf": content.startswith(b"%PDF-"),
        ".txt": _is_utf8_text(content),
    }
    if not valid_content.get(extension, False):
        raise HTTPException(status_code=415, detail={"code": "FILE_CONTENT_INVALID", "message": "File contents do not match an allowed type"})
    file_id = f"file-{uuid4().hex}"
    stored_name = f"{file_id}{extension}"
    directory = Path(UPLOAD_DIRECTORY)
    directory.mkdir(parents=True, exist_ok=True)
    (directory / stored_name).write_bytes(content)
    from .database import engine
    from sqlalchemy.orm import Session
    with Session(engine) as session:
        session.add(FileObject(id=file_id, owner_user_id=user.id, original_name=Path(file.filename or "file").name, stored_name=stored_name, content_type=file.content_type or "application/octet-stream", size=len(content), created_at=datetime.now(timezone.utc)))
        session.commit()
    return {"file": {"file_id": file_id, "name": Path(file.filename or "file").name, "content_type": file.content_type, "size": len(content)}}


def _is_utf8_text(content: bytes) -> bool:
    try:
        content.decode("utf-8")
        return b"\x00" not in content
    except UnicodeDecodeError:
        return False


@router.get("/files/{file_id}")
def download_file(file_id: str, user: User = Depends(bearer_user)) -> FileResponse:
    metadata = get_file(file_id)
    if metadata is None or not is_member_for_file(metadata, user.id):
        raise HTTPException(status_code=404, detail={"code": "FILE_NOT_FOUND", "message": "File not found"})
    path = Path(UPLOAD_DIRECTORY) / metadata.stored_name
    if not path.exists():
        raise HTTPException(status_code=404, detail={"code": "FILE_NOT_FOUND", "message": "File not found"})
    return FileResponse(path, media_type=metadata.content_type, filename=metadata.original_name)


def is_member_for_file(metadata: FileObject, user_id: int) -> bool:
    from .database import Session, engine
    from sqlalchemy import select
    with Session(engine) as session:
        return session.scalar(
            select(Message.sequence_id)
            .join(Membership, Message.room_id == Membership.room_id)
            .where(
                Message.file_id == metadata.id,
                Membership.user_id == user_id,
                Message.sequence_id > Membership.joined_sequence_id,
            )
        ) is not None
