from __future__ import annotations

import httpx
import pytest
import respx

from app.clients.grok2api_client import Grok2ApiClient
from app.providers.grok2api import GrokProvider


def _token(token: str, status: str, quota: int = 0, **extra) -> dict:
    base = {
        "token": token,
        "status": status,
        "quota": quota,
        "consumed": 0,
        "use_count": 0,
        "fail_count": 0,
        "tags": [],
    }
    base.update(extra)
    return base


@respx.mock
@pytest.mark.asyncio
async def test_aggregation(grok_client_cfg, grok_provider_cfg) -> None:
    respx.get("http://grok.test/v1/admin/tokens").mock(
        return_value=httpx.Response(
            200,
            json={
                "tokens": {
                    "ssoBasic": [
                        _token("AAAA1111", "active", 80),
                        _token("BBBB2222", "active", 40),
                        _token("CCCC3333", "cooling", 0),
                        _token("DDDD4444", "expired", 0),
                        _token("EEEE5555", "disabled", 0),
                    ]
                },
                "consumed_mode_enabled": False,
            },
        )
    )

    client = Grok2ApiClient(grok_client_cfg)
    provider = GrokProvider(grok_provider_cfg, client)
    try:
        caps = await provider.fetch_capacity()
    finally:
        await client.aclose()

    assert len(caps) == 1
    cap = caps[0]
    assert cap.pool_name == "ssoBasic"
    assert cap.accounts_total == 5
    assert cap.accounts_active == 2
    assert cap.accounts_cooling == 1
    assert cap.accounts_expired == 1
    assert cap.accounts_disabled == 1
    assert cap.concurrency_total == 2  # active
    assert cap.concurrency_used == 1  # cooling
    assert cap.concurrency_remaining == 1
    assert cap.quota_remaining == 120.0  # 80 + 40
    assert cap.healthy is True
    # 脱敏：tail=4
    assert all(len(a.id) == 4 for a in cap.accounts)


@respx.mock
@pytest.mark.asyncio
async def test_unhealthy_on_upstream_error(grok_client_cfg, grok_provider_cfg) -> None:
    respx.get("http://grok.test/v1/admin/tokens").mock(
        return_value=httpx.Response(503)
    )
    client = Grok2ApiClient(grok_client_cfg)
    provider = GrokProvider(grok_provider_cfg, client)
    try:
        caps = await provider.fetch_capacity()
    finally:
        await client.aclose()
    assert len(caps) == 1
    assert caps[0].healthy is False
    assert caps[0].error


@respx.mock
@pytest.mark.asyncio
async def test_cooling_not_counted_when_disabled(
    grok_client_cfg, grok_provider_cfg
) -> None:
    grok_provider_cfg.cooling_counts_as_used_concurrency = False
    respx.get("http://grok.test/v1/admin/tokens").mock(
        return_value=httpx.Response(
            200,
            json={
                "tokens": {
                    "ssoSuper": [
                        _token("x" * 16, "active", 140),
                        _token("y" * 16, "cooling", 0),
                    ]
                }
            },
        )
    )
    client = Grok2ApiClient(grok_client_cfg)
    provider = GrokProvider(grok_provider_cfg, client)
    try:
        caps = await provider.fetch_capacity()
    finally:
        await client.aclose()
    cap = caps[0]
    assert cap.concurrency_used == 0
    assert cap.concurrency_total == 1
    assert cap.concurrency_remaining == 1
