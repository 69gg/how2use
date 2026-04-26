"""HTTP 路由"""
from __future__ import annotations

import time

from fastapi import APIRouter, Depends, HTTPException, Request

from app.core.auth import verify_server_api_key
from app.providers.base import ProviderCapacity, UpstreamProvider

router = APIRouter()


def _now_ms() -> int:
    return int(time.time() * 1000)


def _providers(request: Request) -> dict[str, UpstreamProvider]:
    return request.app.state.providers


def _cache(request: Request):
    return request.app.state.cache


async def _fetch_provider(
    provider: UpstreamProvider,
    cache,
) -> list[ProviderCapacity]:
    return await cache.get_or_fetch(
        (provider.name,),
        provider.fetch_capacity,
    )


@router.get("/health")
async def health() -> dict:
    return {"status": "ok"}


@router.get("/providers")
async def list_providers(request: Request) -> dict:
    return {"providers": sorted(_providers(request).keys())}


@router.get("/capacity")
async def get_all_capacity(request: Request) -> dict:
    providers = _providers(request)
    cache = _cache(request)
    out: list[ProviderCapacity] = []
    for p in providers.values():
        out.extend(await _fetch_provider(p, cache))
    return {"fetched_at": _now_ms(), "providers": [c.model_dump() for c in out]}


@router.get("/capacity/{provider}")
async def get_provider_capacity(provider: str, request: Request) -> dict:
    p = _providers(request).get(provider)
    if p is None:
        raise HTTPException(status_code=404, detail=f"provider '{provider}' not found")
    items = await _fetch_provider(p, _cache(request))
    return {
        "fetched_at": _now_ms(),
        "providers": [c.model_dump() for c in items],
    }


@router.get("/capacity/{provider}/{pool}")
async def get_pool_capacity(provider: str, pool: str, request: Request) -> dict:
    p = _providers(request).get(provider)
    if p is None:
        raise HTTPException(status_code=404, detail=f"provider '{provider}' not found")
    items = await _fetch_provider(p, _cache(request))
    matched = [c for c in items if (c.pool_name or "") == pool]
    if not matched:
        raise HTTPException(
            status_code=404,
            detail=f"pool '{pool}' not found under provider '{provider}'",
        )
    return {
        "fetched_at": _now_ms(),
        "providers": [c.model_dump() for c in matched],
    }


@router.post("/refresh", dependencies=[Depends(verify_server_api_key)])
async def refresh_all(request: Request) -> dict:
    _cache(request).invalidate_all()
    return {"status": "ok"}


@router.post("/refresh/{provider}", dependencies=[Depends(verify_server_api_key)])
async def refresh_provider(provider: str, request: Request) -> dict:
    if provider not in _providers(request):
        raise HTTPException(status_code=404, detail=f"provider '{provider}' not found")
    _cache(request).invalidate_prefix(provider)
    return {"status": "ok", "provider": provider}


__all__ = ["router"]
