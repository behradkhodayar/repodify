"""Bearer-token auth dependency for the single-user API."""

from __future__ import annotations

from collections.abc import Callable

from fastapi import Header, HTTPException, status


def make_require_token(expected: str | None) -> Callable[[str | None], None]:
    """Build a dependency that enforces `Authorization: Bearer <expected>`.

    A no-op when `expected` is None (auth disabled, dev-only).
    """

    def require_token(authorization: str | None = Header(default=None)) -> None:
        if expected is None:
            return
        if authorization != f"Bearer {expected}":
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="invalid or missing token",
                headers={"WWW-Authenticate": "Bearer"},
            )

    return require_token
