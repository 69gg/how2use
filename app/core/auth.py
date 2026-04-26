"""X-API-Key 鉴权依赖"""
from __future__ import annotations

from fastapi import Header, HTTPException, status

from .config import get_config


async def verify_server_api_key(
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
) -> None:
    expected = get_config().server.api_key
    if not expected:
        return
    if x_api_key != expected:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="invalid or missing X-API-Key",
        )


__all__ = ["verify_server_api_key"]
