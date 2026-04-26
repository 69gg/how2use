from __future__ import annotations

import time

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.routes import router
from app.cache import CapacityCache
from app.core import config as cfg_mod
from app.providers.base import ProviderCapacity


class StubProvider:
    def __init__(self, name: str, caps: list[ProviderCapacity]) -> None:
        self.name = name
        self._caps = caps
        self.fetch_count = 0

    async def fetch_capacity(self) -> list[ProviderCapacity]:
        self.fetch_count += 1
        return list(self._caps)

    async def aclose(self) -> None:
        pass


def _build_app(providers, api_key: str = "") -> FastAPI:
    cfg_mod.reset_config_cache()
    # 通过环境变量注入 api_key；但 lru_cache 已清，下次 get_config() 会重读
    import os

    if api_key:
        os.environ["HOW2USE_SERVER__API_KEY"] = api_key
    else:
        os.environ.pop("HOW2USE_SERVER__API_KEY", None)
    cfg_mod.reset_config_cache()

    app = FastAPI()
    app.include_router(router)
    app.state.providers = {p.name: p for p in providers}
    app.state.cache = CapacityCache(ttl_seconds=5)
    return app


def _cap(provider: str, pool: str) -> ProviderCapacity:
    return ProviderCapacity(
        provider=provider,
        pool_name=pool,
        accounts_total=1,
        accounts_active=1,
        concurrency_total=1,
        concurrency_remaining=1,
        fetched_at=int(time.time() * 1000),
        healthy=True,
    )


def test_health_and_providers() -> None:
    p1 = StubProvider("grok2api", [_cap("grok2api", "ssoBasic")])
    p2 = StubProvider("nim", [_cap("nim", "default")])
    app = _build_app([p1, p2])
    with TestClient(app) as c:
        assert c.get("/health").json() == {"status": "ok"}
        assert c.get("/providers").json() == {"providers": ["grok2api", "nim"]}


def test_capacity_endpoints_and_caching() -> None:
    p = StubProvider("grok2api", [_cap("grok2api", "ssoBasic")])
    app = _build_app([p])
    with TestClient(app) as c:
        r1 = c.get("/capacity/grok2api").json()
        r2 = c.get("/capacity/grok2api").json()
        # 缓存命中：fetch_capacity 只调用一次
        assert p.fetch_count == 1
        assert r1["providers"][0]["provider"] == "grok2api"
        assert r2["providers"][0]["pool_name"] == "ssoBasic"

        r3 = c.get("/capacity/grok2api/ssoBasic")
        assert r3.status_code == 200
        assert c.get("/capacity/grok2api/missing").status_code == 404
        assert c.get("/capacity/unknown").status_code == 404


def test_refresh_with_api_key() -> None:
    p = StubProvider("grok2api", [_cap("grok2api", "ssoBasic")])
    app = _build_app([p], api_key="secret")
    with TestClient(app) as c:
        # 无 key → 401
        assert c.post("/refresh").status_code == 401
        # 错 key → 401
        assert c.post("/refresh", headers={"X-API-Key": "wrong"}).status_code == 401
        # 正确 key → 200
        assert (
            c.post("/refresh", headers={"X-API-Key": "secret"}).status_code == 200
        )

        # 刷新后再请求会重新 fetch
        c.get("/capacity/grok2api")
        c.post("/refresh", headers={"X-API-Key": "secret"})
        c.get("/capacity/grok2api")
        assert p.fetch_count == 2
