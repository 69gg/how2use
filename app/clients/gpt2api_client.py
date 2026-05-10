"""gpt2api HTTP 客户端

参考接口：
- GET /v1/admin/tokens   (Bearer 鉴权)
"""
from __future__ import annotations

import httpx

from app.core.config import Gpt2ApiClientConfig
from app.core.http_client import make_client
from app.providers.base import AuthError, UpstreamError


class Gpt2ApiClient:
    """gpt2api 上游管理接口客户端"""

    def __init__(self, cfg: Gpt2ApiClientConfig) -> None:
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
            raise UpstreamError(f"gpt2api /health failed: {e}") from e
        return resp.status_code == 200

    async def get_tokens(self) -> dict[str, list[dict]]:
        """返回 ``{pool_name: [token_info_dict, ...]}``

        gpt2api 响应外层是 ``{"tokens": {...}}``，本方法只返回 tokens 部分。
        """
        try:
            resp = await self._client.get("/v1/admin/tokens")
        except httpx.TimeoutException as e:
            raise UpstreamError(f"gpt2api /v1/admin/tokens timeout: {e}") from e
        except httpx.HTTPError as e:
            raise UpstreamError(f"gpt2api /v1/admin/tokens network error: {e}") from e

        if resp.status_code in (401, 403):
            raise AuthError(
                f"gpt2api auth failed (status={resp.status_code}): check app_key"
            )
        if resp.status_code >= 400:
            raise UpstreamError(
                f"gpt2api /v1/admin/tokens HTTP {resp.status_code}: {resp.text[:200]}"
            )

        try:
            payload = resp.json()
        except ValueError as e:
            raise UpstreamError(f"gpt2api response not JSON: {e}") from e

        tokens = payload.get("tokens") or {}
        if not isinstance(tokens, dict):
            raise UpstreamError(
                f"gpt2api response 'tokens' not a dict: {type(tokens).__name__}"
            )
        return tokens


__all__ = ["Gpt2ApiClient"]