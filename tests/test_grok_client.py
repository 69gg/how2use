from __future__ import annotations

import httpx
import pytest
import respx

from app.clients.grok2api_client import Grok2ApiClient
from app.providers.base import AuthError, UpstreamError


@respx.mock
@pytest.mark.asyncio
async def test_get_tokens_ok(grok_client_cfg) -> None:
    respx.get("http://grok.test/v1/admin/tokens").mock(
        return_value=httpx.Response(
            200,
            json={
                "tokens": {
                    "ssoBasic": [{"token": "abcd1234", "status": "active", "quota": 80}]
                },
                "consumed_mode_enabled": False,
            },
        )
    )
    client = Grok2ApiClient(grok_client_cfg)
    try:
        result = await client.get_tokens()
    finally:
        await client.aclose()
    assert "ssoBasic" in result
    assert result["ssoBasic"][0]["status"] == "active"


@respx.mock
@pytest.mark.asyncio
async def test_get_tokens_auth_error(grok_client_cfg) -> None:
    respx.get("http://grok.test/v1/admin/tokens").mock(
        return_value=httpx.Response(401, json={"detail": "Invalid"})
    )
    client = Grok2ApiClient(grok_client_cfg)
    try:
        with pytest.raises(AuthError):
            await client.get_tokens()
    finally:
        await client.aclose()


@respx.mock
@pytest.mark.asyncio
async def test_get_tokens_5xx(grok_client_cfg) -> None:
    respx.get("http://grok.test/v1/admin/tokens").mock(
        return_value=httpx.Response(503, text="down")
    )
    client = Grok2ApiClient(grok_client_cfg)
    try:
        with pytest.raises(UpstreamError):
            await client.get_tokens()
    finally:
        await client.aclose()


@respx.mock
@pytest.mark.asyncio
async def test_health(grok_client_cfg) -> None:
    respx.get("http://grok.test/health").mock(
        return_value=httpx.Response(200, json={"status": "ok"})
    )
    client = Grok2ApiClient(grok_client_cfg)
    try:
        assert await client.health() is True
    finally:
        await client.aclose()
