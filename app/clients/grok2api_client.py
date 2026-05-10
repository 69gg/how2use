"""grok2api HTTP 客户端

参考接口：
- GET /v1/admin/tokens   (Bearer 鉴权)
  ``/data0/grok2api/app/api/v1/admin/token.py:104``
- GET /health
"""
from __future__ import annotations

import httpx

from app.core.config import Grok2ApiClientConfig
from app.core.http_client import make_client
from app.providers.base import AuthError, UpstreamError


class Grok2ApiClient:
    """grok2api 上游管理接口客户端（最小封装）"""

    def __init__(self, cfg: Grok2ApiClientConfig) -> None:
        self.cfg = cfg
        self._client = make_client(
            base_url=cfg.base_url,
            timeout=cfg.timeout,
            max_connections=cfg.max_connections,
            headers={"Authorization": f"Bearer {cfg.app_key}"} if cfg.app_key else {},
        )

    async def aclose(self) -> None:
        await self._client.aclose()

    async def health(self) -> bool:
        try:
            resp = await self._client.get("/health")
        except httpx.HTTPError as e:
            raise UpstreamError(f"grok2api /health failed: {e}") from e
        return resp.status_code == 200

    async def get_tokens(self) -> dict[str, list[dict]]:
        """返回 ``{pool_name: [token_info_dict, ...]}``

        注意：grok2api 的响应外层是 ``{"tokens": {...}, "consumed_mode_enabled": bool}``
        本方法只返回 tokens 部分。
        """
        try:
            resp = await self._client.get("/v1/admin/tokens")
        except httpx.TimeoutException as e:
            raise UpstreamError(f"grok2api /v1/admin/tokens timeout: {e}") from e
        except httpx.HTTPError as e:
            raise UpstreamError(f"grok2api /v1/admin/tokens network error: {e}") from e

        if resp.status_code in (401, 403):
            raise AuthError(
                f"grok2api auth failed (status={resp.status_code}): check app_key"
            )
        if resp.status_code >= 400:
            raise UpstreamError(
                f"grok2api /v1/admin/tokens HTTP {resp.status_code}: {resp.text[:200]}"
            )

        try:
            payload = resp.json()
        except ValueError as e:
            raise UpstreamError(f"grok2api response not JSON: {e}") from e

        tokens = payload.get("tokens") or {}
        if not isinstance(tokens, dict):
            raise UpstreamError(
                f"grok2api response 'tokens' not a dict: {type(tokens).__name__}"
            )
        return tokens

    async def get_token_counts(self) -> dict[str, dict]:
        """返回 ``{pool_name: {total, active, cooling, expired, disabled}}``

        轻量端点，不传输完整 token 数据。
        对应 grok2api ``GET /v1/admin/tokens/counts``
        """
        try:
            resp = await self._client.get("/v1/admin/tokens/counts")
        except httpx.TimeoutException as e:
            raise UpstreamError(f"grok2api /v1/admin/tokens/counts timeout: {e}") from e
        except httpx.HTTPError as e:
            raise UpstreamError(f"grok2api /v1/admin/tokens/counts network error: {e}") from e

        if resp.status_code in (401, 403):
            raise AuthError(
                f"grok2api auth failed (status={resp.status_code}): check app_key"
            )
        if resp.status_code >= 400:
            raise UpstreamError(
                f"grok2api /v1/admin/tokens/counts HTTP {resp.status_code}: {resp.text[:200]}"
            )

        try:
            payload = resp.json()
        except ValueError as e:
            raise UpstreamError(f"grok2api response not JSON: {e}") from e

        pools = payload.get("pools") or {}
        if not isinstance(pools, dict):
            raise UpstreamError(
                f"grok2api response 'pools' not a dict: {type(pools).__name__}"
            )
        return pools


__all__ = ["Grok2ApiClient"]
