"""
Security utilities: password hashing, JWT creation/verification, API key generation.
"""

from __future__ import annotations

import hashlib
import secrets
import uuid
from datetime import datetime, timedelta, timezone

from jose import JWTError, jwt
from passlib.context import CryptContext

from mtgs.config import settings

_pwd_ctx = CryptContext(schemes=["bcrypt"], deprecated="auto")

# Roles ordered by privilege level (higher index = more privilege)
ROLE_ORDER = ["viewer", "developer", "reviewer", "admin"]


# ── Password ──────────────────────────────────────────────────────────────────

def hash_password(password: str) -> str:
    return _pwd_ctx.hash(password)


def verify_password(plain: str, hashed: str) -> bool:
    return _pwd_ctx.verify(plain, hashed)


# ── JWT ───────────────────────────────────────────────────────────────────────

def create_access_token(
    subject: str,
    org_id: str,
    role: str,
    expires_delta: timedelta | None = None,
) -> str:
    expire = datetime.now(timezone.utc) + (
        expires_delta
        or timedelta(minutes=settings.jwt_access_token_expire_minutes)
    )
    payload = {
        "sub": subject,
        "org_id": org_id,
        "role": role,
        "exp": expire,
        "iat": datetime.now(timezone.utc),
        "type": "access",
    }
    return jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


def decode_access_token(token: str) -> dict:
    """
    Decode and validate a JWT.
    Raises JWTError on invalid/expired token.
    """
    return jwt.decode(token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm])


# ── API Key ───────────────────────────────────────────────────────────────────

def generate_api_key() -> tuple[str, str, str]:
    """
    Generate a new API key.

    Returns:
        (raw_key, key_prefix, key_hash)
        - raw_key   : shown ONCE to the user (e.g., 'mtgs_abc123...')
        - key_prefix: first 8 chars for display in UI
        - key_hash  : bcrypt hash stored in DB
    """
    raw = f"mtgs_{secrets.token_urlsafe(32)}"
    prefix = raw[:8]
    hashed = _pwd_ctx.hash(raw)
    return raw, prefix, hashed


def verify_api_key(raw_key: str, stored_hash: str) -> bool:
    return _pwd_ctx.verify(raw_key, stored_hash)


# ── RBAC ──────────────────────────────────────────────────────────────────────

def has_minimum_role(user_role: str, required_role: str) -> bool:
    """Check if user_role is at least as privileged as required_role."""
    try:
        return ROLE_ORDER.index(user_role) >= ROLE_ORDER.index(required_role)
    except ValueError:
        return False
