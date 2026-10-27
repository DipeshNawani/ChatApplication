from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, create_engine, func, select
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, relationship

from .config import DATABASE_PATH, GENERAL_ROOM_ID


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    username: Mapped[str] = mapped_column(String(32), unique=True, nullable=False, index=True)
    password_hash: Mapped[str] = mapped_column(String(512), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    memberships: Mapped[list["Membership"]] = relationship(back_populates="user", cascade="all, delete-orphan")


class Room(Base):
    __tablename__ = "rooms"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(64), nullable=False)
    kind: Mapped[str] = mapped_column(String(16), nullable=False)
    direct_key: Mapped[str | None] = mapped_column(String(80), unique=True, nullable=True)
    owner_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    is_closed: Mapped[bool] = mapped_column(default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    memberships: Mapped[list["Membership"]] = relationship(back_populates="room", cascade="all, delete-orphan")
    messages: Mapped[list["Message"]] = relationship(back_populates="room")


class Membership(Base):
    __tablename__ = "memberships"
    __table_args__ = (UniqueConstraint("room_id", "user_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    room_id: Mapped[str] = mapped_column(ForeignKey("rooms.id"), nullable=False, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    joined_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    joined_sequence_id: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    room: Mapped[Room] = relationship(back_populates="memberships")
    user: Mapped[User] = relationship(back_populates="memberships")


class Message(Base):
    __tablename__ = "messages"
    __table_args__ = (UniqueConstraint("sender_user_id", "client_message_id"),)

    sequence_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    message_id: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    room_id: Mapped[str] = mapped_column(ForeignKey("rooms.id"), nullable=False, index=True)
    sender_user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    client_message_id: Mapped[str] = mapped_column(String(128), nullable=False)
    kind: Mapped[str] = mapped_column(String(16), nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    file_id: Mapped[str | None] = mapped_column(ForeignKey("files.id"), nullable=True)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    room: Mapped[Room] = relationship(back_populates="messages")
    sender: Mapped[User] = relationship()


class FileObject(Base):
    __tablename__ = "files"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    owner_user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    original_name: Mapped[str] = mapped_column(String(255), nullable=False)
    stored_name: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    content_type: Mapped[str] = mapped_column(String(100), nullable=False)
    size: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


def get_file(file_id: str) -> FileObject | None:
    with Session(engine) as session:
        return session.get(FileObject, file_id)


def message_belongs_to_room(message_id: str, room_id: str) -> bool:
    with Session(engine) as session:
        return session.scalar(select(Message.sequence_id).where(Message.message_id == message_id, Message.room_id == room_id)) is not None


def _database_url(database_path: str) -> str:
    if database_path.startswith("postgres://"):
        return database_path.replace("postgres://", "postgresql+psycopg://", 1)
    if database_path.startswith("postgresql://"):
        return database_path.replace("postgresql://", "postgresql+psycopg://", 1)
    if "://" in database_path:
        return database_path
    return f"sqlite:///{Path(database_path).resolve().as_posix()}"


engine = create_engine(_database_url(DATABASE_PATH), future=True)


def configure_database(database_path: str) -> None:
    global engine
    resolved_path = database_path.removeprefix("sqlite:///") if database_path.startswith("sqlite:") else database_path
    if "://" not in database_path or database_path.startswith("sqlite:"):
        Path(resolved_path).parent.mkdir(parents=True, exist_ok=True)
    engine.dispose()
    engine = create_engine(_database_url(database_path), future=True)


def init_database(create_schema: bool = False) -> None:
    if create_schema:
        Base.metadata.create_all(engine)
    with Session(engine) as session:
        if session.get(Room, GENERAL_ROOM_ID) is None:
            session.add(Room(id=GENERAL_ROOM_ID, name="general", kind="general", is_closed=False, created_at=datetime.now(timezone.utc)))
            session.commit()


def dispose_database() -> None:
    engine.dispose()


def create_user(username: str, password_hash: str) -> User:
    with Session(engine) as session:
        user = User(username=username, password_hash=password_hash, created_at=datetime.now(timezone.utc))
        session.add(user)
        session.flush()
        general = session.get(Room, GENERAL_ROOM_ID)
        session.add(Membership(room=general, user=user, joined_at=datetime.now(timezone.utc)))
        session.commit()
        session.refresh(user)
        return user


def get_user_by_username(username: str) -> User | None:
    with Session(engine) as session:
        return session.scalar(select(User).where(User.username == username.lower()))


def get_user_by_id(user_id: int) -> User | None:
    with Session(engine) as session:
        return session.get(User, user_id)


def search_users(query: str, current_user_id: int, limit: int = 20) -> list[User]:
    with Session(engine) as session:
        escaped = query.lower().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        return list(
            session.scalars(
                select(User)
                .where(User.id != current_user_id, User.username.like(f"%{escaped}%", escape="\\"))
                .order_by(User.username)
                .limit(limit)
            )
        )


def is_member(room_id: str, user_id: int) -> bool:
    with Session(engine) as session:
        return session.scalar(
            select(Membership.id).where(Membership.room_id == room_id, Membership.user_id == user_id)
        ) is not None


def get_room(room_id: str) -> Room | None:
    with Session(engine) as session:
        return session.get(Room, room_id)


def get_or_create_direct_room(first_user_id: int, second_user_id: int) -> tuple[Room, bool]:
    user_ids = sorted((first_user_id, second_user_id))
    direct_key = f"{user_ids[0]}:{user_ids[1]}"
    with Session(engine) as session:
        room = session.scalar(select(Room).where(Room.direct_key == direct_key))
        room_created = False
        if room is None:
            room_created = True
            room = Room(id=f"direct-{uuid4().hex[:24]}", name="direct", kind="direct", direct_key=direct_key, created_at=datetime.now(timezone.utc))
            session.add(room)
            session.add_all([
                Membership(room=room, user_id=user_ids[0], joined_at=datetime.now(timezone.utc), joined_sequence_id=0),
                Membership(room=room, user_id=user_ids[1], joined_at=datetime.now(timezone.utc), joined_sequence_id=0),
            ])
            session.commit()
            session.refresh(room)
        return room, room_created


def create_group_room(owner_id: int, name: str) -> Room:
    with Session(engine) as session:
        room = Room(id=f"group-{uuid4().hex[:24]}", name=name, kind="group", owner_id=owner_id, created_at=datetime.now(timezone.utc))
        session.add(room)
        session.add(Membership(room=room, user_id=owner_id, joined_at=datetime.now(timezone.utc), joined_sequence_id=0))
        session.commit()
        session.refresh(room)
        return room


def add_member(room_id: str, user_id: int, max_members: int = 50) -> bool:
    with Session(engine) as session:
        room = session.get(Room, room_id)
        if room is None or room.kind != "group" or room.is_closed:
            return False
        count = session.scalar(select(func.count(Membership.id)).where(Membership.room_id == room_id)) or 0
        if count >= max_members or session.scalar(select(Membership.id).where(Membership.room_id == room_id, Membership.user_id == user_id)):
            return False
        latest = session.scalar(select(func.max(Message.sequence_id)).where(Message.room_id == room_id)) or 0
        session.add(Membership(room_id=room_id, user_id=user_id, joined_at=datetime.now(timezone.utc), joined_sequence_id=latest))
        session.commit()
        return True


def remove_member(room_id: str, user_id: int, actor_id: int) -> tuple[bool, int | None, bool]:
    with Session(engine) as session:
        room = session.get(Room, room_id)
        membership = session.scalar(select(Membership).where(Membership.room_id == room_id, Membership.user_id == user_id))
        if room is None or room.kind != "group" or (actor_id != user_id and room.owner_id != actor_id) or membership is None:
            return False, None, False
        session.delete(membership)
        remaining = list(session.scalars(select(Membership).where(Membership.room_id == room_id, Membership.user_id != user_id).order_by(Membership.joined_at)))
        if not remaining:
            room.is_closed = True
            session.commit()
            return True, None, True
        if room.owner_id == user_id:
            room.owner_id = remaining[0].user_id
        session.commit()
        return True, room.owner_id, False


def list_rooms(user_id: int) -> list[dict[str, str]]:
    with Session(engine) as session:
        memberships = session.scalars(
            select(Membership).join(Room).where(Membership.user_id == user_id, Room.is_closed.is_(False)).order_by(Membership.joined_at)
        ).all()
        rooms = []
        for membership in memberships:
            name = membership.room.name
            if membership.room.kind == "direct":
                other = next((item.user for item in membership.room.memberships if item.user_id != user_id), None)
                name = other.username if other else name
            rooms.append({"room_id": membership.room.id, "name": name, "kind": membership.room.kind})
        return rooms


def save_message(room_id: str, sender_user_id: int, client_message_id: str, kind: str, text: str, file_id: str | None = None) -> dict[str, str | int | bool]:
    with Session(engine) as session:
        existing = session.scalar(
            select(Message).where(Message.sender_user_id == sender_user_id, Message.client_message_id == client_message_id)
        )
        if existing:
            return _message_dict(existing, created=False)
        message = Message(
            message_id=f"msg-{uuid4().hex[:12]}",
            room_id=room_id,
            sender_user_id=sender_user_id,
            client_message_id=client_message_id,
            kind=kind,
            text=text,
            file_id=file_id,
            occurred_at=datetime.now(timezone.utc),
        )
        session.add(message)
        session.commit()
        session.refresh(message)
        return _message_dict(message, created=True)


def get_history(room_id: str, user_id: int, limit: int, before: int | None, after: int | None) -> tuple[list[dict[str, str | int | None]], bool]:
    with Session(engine) as session:
        membership = session.scalar(select(Membership).where(Membership.room_id == room_id, Membership.user_id == user_id))
        filters = [Message.room_id == room_id, Message.sequence_id > (membership.joined_sequence_id if membership else 0)]
        if before is not None:
            filters.append(Message.sequence_id < before)
        if after is not None:
            filters.append(Message.sequence_id > after)
        if after is not None:
            query = select(Message).where(*filters).order_by(Message.sequence_id.asc()).limit(limit + 1)
            rows = list(session.scalars(query).all())
        else:
            query = select(Message).where(*filters).order_by(Message.sequence_id.desc()).limit(limit + 1)
            rows = list(reversed(session.scalars(query).all()))
        has_more = len(rows) > limit
        selected = rows[:limit] if after is not None else rows[-limit:]
        return [_message_dict(message, created=True) for message in selected], has_more


def _message_dict(message: Message, created: bool) -> dict[str, str | int | bool]:
    occurred_at = message.occurred_at
    if occurred_at.tzinfo is None:
        occurred_at = occurred_at.replace(tzinfo=timezone.utc)
    return {
        "sequence_id": message.sequence_id,
        "message_id": message.message_id,
        "room_id": message.room_id,
        "sender_user_id": message.sender_user_id,
        "sender_username": message.sender.username if message.sender else None,
        "client_message_id": message.client_message_id,
        "kind": message.kind,
        "text": message.text,
        "file_id": message.file_id,
        "occurred_at": occurred_at.isoformat().replace("+00:00", "Z"),
        "created": created,
    }
