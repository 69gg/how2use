"""httpx.AsyncClient 工厂"""
from __future__ import annotations

import httpx


def make_client(
    base_url: str,
    timeout: float,
    max_connections: int,
    headers: dict[str, str] | None = None,
) -> httpx.AsyncClient:
    limits = httpx.Limits(
        max_connections=max_connections,
        max_keepalive_connections=max_connections,
    )
    return httpx.AsyncClient(
        base_url=base_url.rstrip("/"),
        timeout=httpx.Timeout(timeout),
        limits=limits,
        headers=headers or {},
    )


__all__ = ["make_client"]
