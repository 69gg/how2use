from __future__ import annotations

import httpx
import pytest
import respx

from app.clients.new_api_client import NewApiClient, NewApiError
from app.providers.base import AuthError


@respx.mock
@pytest.mark.asyncio
async def test_dual_header_injected(new_api_client_cfg) -> None:
    route = respx.get("http://newapi.test/api/channel/42").mock(
        return_value=httpx.Response(
            200,
            json={
                "success": True,
                "data": {
                    "id": 42,
                    "status": 1,
                    "channel_info": '{"is_multi_key": true, "multi_key_size": 3, "multi_key_status_list": {"0": 0, "1": 0, "2": 1}}',
                },
            },
        )
    )
    client = NewApiClient(new_api_client_cfg)
    try:
        data = await client.get_channel(42)
    finally:
        await client.aclose()

    req = route.calls.last.request
    assert req.headers.get("Authorization") == "Bearer acc-token"
    assert req.headers.get("New-Api-User") == "42"
    # channel_info JSON 字符串被解析为 dict
    assert isinstance(data["channel_info"], dict)
    assert data["channel_info"]["multi_key_size"] == 3


@respx.mock
@pytest.mark.asyncio
async def test_get_log_stat(new_api_client_cfg) -> None:
    respx.get("http://newapi.test/api/log/stat").mock(
        return_value=httpx.Response(
            200,
            json={"success": True, "data": {"quota": 100, "rpm": 12, "tpm": 3400}},
        )
    )
    client = NewApiClient(new_api_client_cfg)
    try:
        rpm, tpm = await client.get_log_stat(42)
    finally:
        await client.aclose()
    assert (rpm, tpm) == (12, 3400)


@respx.mock
@pytest.mark.asyncio
async def test_get_log_stat_multi_sums(new_api_client_cfg) -> None:
    respx.get("http://newapi.test/api/log/stat", params={"channel": 1, "type": 2}).mock(
        return_value=httpx.Response(
            200, json={"success": True, "data": {"rpm": 5, "tpm": 100}}
        )
    )
    respx.get("http://newapi.test/api/log/stat", params={"channel": 2, "type": 2}).mock(
        return_value=httpx.Response(
            200, json={"success": True, "data": {"rpm": 7, "tpm": 250}}
        )
    )
    client = NewApiClient(new_api_client_cfg)
    try:
        rpm, tpm = await client.get_log_stat_multi([1, 2])
    finally:
        await client.aclose()
    assert (rpm, tpm) == (12, 350)


@respx.mock
@pytest.mark.asyncio
async def test_auth_error(new_api_client_cfg) -> None:
    respx.get("http://newapi.test/api/channel/1").mock(
        return_value=httpx.Response(401, json={"success": False, "message": "unauthorized"})
    )
    client = NewApiClient(new_api_client_cfg)
    try:
        with pytest.raises(AuthError):
            await client.get_channel(1)
    finally:
        await client.aclose()


@respx.mock
@pytest.mark.asyncio
async def test_business_error(new_api_client_cfg) -> None:
    respx.get("http://newapi.test/api/channel/1").mock(
        return_value=httpx.Response(
            200, json={"success": False, "message": "channel not found"}
        )
    )
    client = NewApiClient(new_api_client_cfg)
    try:
        with pytest.raises(NewApiError):
            await client.get_channel(1)
    finally:
        await client.aclose()
