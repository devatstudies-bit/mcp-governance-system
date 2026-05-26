"""
FastAPI auth dependencies.

Usage:
    @router.get("/tools")
    async def list_tools(
        current_user: CurrentUser = Depends(require_role("developer")),
        db: AsyncSession = Depends(get_db),
    ):
        ...
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable

from fastapi import Depends, HTTPException, Security, status
from fastapi.security import APIKeyHeader, HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from mtgs.auth.security import decode_access_token, verify_api_key
from mtgs.database import get_db
from mtgs.models.user import ApiKey, User
from mtgs.utils.logging import get_logger

logger = get_logger(__name__)

# FastAPI security schemes
_bearer_scheme = HTTPBearer(auto_error=False)
_api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


@dataclass
class AuthenticatedUser:
    """Lightweight principal passed through request context."""

    id: uuid.UUID
    email: str
    role: str
    org_id: uuid.UUID
    auth_method: str  # "jwt" | "api_key"


async def get_current_user(
    bearer: HTTPAuthorizationCredentials | None = Security(_bearer_scheme),
    api_key: str | None = Security(_api_key_header),
    db: AsyncSession = Depends(get_db),
) -> AuthenticatedUser:
    """
    Resolve the authenticated user from either a JWT Bearer token or an API key.
    Raises HTTP 401 if neither is valid.
    """
    # ── Try JWT first ─────────────────────────────────────────────────────────
    if bearer is not None:
        try:
            payload = decode_access_token(bearer.credentials)
            user_id = uuid.UUID(payload["sub"])
            result = await db.execute(
                select(User).where(User.id == user_id, User.is_active == True)
            )
            user = result.scalar_one_or_none()
            if user is None:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="User not found or inactive",
                )
            return AuthenticatedUser(
                id=user.id,
                email=user.email,
                role=user.role,
                org_id=user.organization_id,
                auth_method="jwt",
            )
        except JWTError as e:
            logger.warning("jwt_decode_failed", error=str(e))
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid or expired token",
                headers={"WWW-Authenticate": "Bearer"},
            )

    # ── Try API key ───────────────────────────────────────────────────────────
    if api_key is not None:
        prefix = api_key[:8]
        result = await db.execute(
            select(ApiKey)
            .where(
                ApiKey.key_prefix == prefix,
                ApiKey.is_active == True,
            )
        )
        key_records = result.scalars().all()
        for record in key_records:
            if verify_api_key(api_key, record.key_hash):
                # Check expiry
                if record.expires_at and record.expires_at < datetime.now(timezone.utc):
                    raise HTTPException(
                        status_code=status.HTTP_401_UNAUTHORIZED,
                        detail="API key has expired",
                    )
                # Load the owning user
                user_result = await db.execute(
                    select(User).where(User.id == record.user_id, User.is_active == True)
                )
                user = user_result.scalar_one_or_none()
                if user is None:
                    continue
                # Update last_used_at (fire-and-forget; do not block)
                record.last_used_at = datetime.now(timezone.utc)
                return AuthenticatedUser(
                    id=user.id,
                    email=user.email,
                    role=user.role,
                    org_id=user.organization_id,
                    auth_method="api_key",
                )

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Authentication required. Provide Bearer token or X-API-Key header.",
        headers={"WWW-Authenticate": "Bearer"},
    )


# Convenience type alias
CurrentUser = AuthenticatedUser


def require_role(minimum_role: str) -> Callable:
    """
    FastAPI dependency factory. Returns a dependency that enforces a minimum role.

    Usage:
        Depends(require_role("reviewer"))
    """
    async def _check_role(
        user: AuthenticatedUser = Depends(get_current_user),
    ) -> AuthenticatedUser:
        from mtgs.auth.security import has_minimum_role

        if not has_minimum_role(user.role, minimum_role):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"This action requires '{minimum_role}' role or higher.",
            )
        return user

    return _check_role
