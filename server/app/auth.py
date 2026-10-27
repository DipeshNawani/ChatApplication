from datetime import datetime, timedelta, timezone
from typing import Any

import jwt
from fastapi import Header, HTTPException
from pwdlib import PasswordHash

from .config import DEV_MODE, JWT_EXPIRE_MINUTES, JWT_SECRET
from .database import User, get_user_by_id

password_hash = PasswordHash.recommended()


def hash_password(password: str) -> str:
    return password_hash.hash(password)


def verify_password(password: str, stored_hash: str) -> bool:
    return password_hash.verify(password, stored_hash)


def create_access_token(user: User) -> str:
    if len(JWT_SECRET) < 32:
        raise RuntimeError("JWT_SECRET must be at least 32 characters")
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(user.id),
        "username": user.username,
        "iat": now,
        "exp": now + timedelta(minutes=JWT_EXPIRE_MINUTES),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm="HS256")


def decode_token(token: str) -> dict[str, Any]:
    if len(JWT_SECRET) < 32:
        raise jwt.InvalidTokenError("JWT secret is not configured or too short")
    return jwt.decode(token, JWT_SECRET, algorithms=["HS256"])


def user_from_token(token: str) -> User:
    try:
        payload = decode_token(token)
        user_id = int(payload["sub"])
    except (jwt.PyJWTError, KeyError, TypeError, ValueError) as error:
        raise HTTPException(status_code=401, detail="Invalid or expired token") from error
    user = get_user_by_id(user_id)
    if user is None:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    return user


def bearer_user(authorization: str | None = Header(default=None)) -> User:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Authentication required")
    return user_from_token(authorization.removeprefix("Bearer ").strip())
