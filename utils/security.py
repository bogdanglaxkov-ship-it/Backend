import hashlib
import os
import secrets
from datetime import datetime, timedelta, timezone

from jose import jwt
from passlib.context import CryptContext

JWT_SECRET = os.environ["JWT_SECRET"]  # fail fast if not set
JWT_ALGORITHM = "HS256"
JWT_EXPIRES_MINUTES = int(os.environ.get("JWT_EXPIRES_MINUTES", "10080"))  # 7 days

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


# ---------------------------------------------------------------------------
# Passwords
# ---------------------------------------------------------------------------

def hash_password(raw_password: str) -> str:
    return pwd_context.hash(raw_password)


def verify_password(raw_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(raw_password, hashed_password)


# ---------------------------------------------------------------------------
# Session JWT
# ---------------------------------------------------------------------------

def sign_auth_token(user_id: str, email: str) -> str:
    payload = {
        "userId": user_id,
        "email": email,
        "exp": datetime.now(timezone.utc) + timedelta(minutes=JWT_EXPIRES_MINUTES),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def verify_auth_token(token: str) -> dict:
    return jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])


# ---------------------------------------------------------------------------
# Single-use tokens (email verification / password reset)
# ---------------------------------------------------------------------------
# We only ever store the SHA-256 hash of these tokens in the DB and email the
# raw token to the user — same pattern as API keys — so a leaked DB dump
# can't be replayed into a valid link.

def generate_raw_token() -> str:
    return secrets.token_hex(32)


def hash_token(raw_token: str) -> str:
    return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()


def token_expiry(hours: int) -> datetime:
    return datetime.utcnow() + timedelta(hours=hours)


def is_expired(expires_at: datetime | None) -> bool:
    return expires_at is None or expires_at < datetime.utcnow()
