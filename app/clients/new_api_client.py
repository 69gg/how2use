"""new-api HTTP 客户端

双 header 鉴权：
- ``Authorization: Bearer <ACCESS_TOKEN>``
- ``New-Api-User: <USER_ID>``
参考 ``/data0/new-api/middleware/auth.go:42,77``

封装两个端点：
- GET /api/channel/:id        ``/data0/new-api/controller/channel.go:361``
- GET /api/log/stat           ``/data0/new-api/controller/log.go:96``
  rpm/tpm 固定 60s 滑窗：``/data0/new-api/model/log.go:423``
"""
from __future__ import annotations

import asyncio
import json
from typing import Any

import httpx

from app.core.config import NewApiClientConfig
from app.core.http_client import make_client
from app.providers.base import AuthError, ProviderError, UpstreamError

LOG_TYPE_CONSUME = 2  # /data0/new-api/model/log.go LogTypeConsume


class NewApiError(ProviderError):
    """new-api 业务错误（success=false）"""

    def __init__(self, message: str, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


class NewApiClient:
    def __init__(self, cfg: NewApiClientConfig) -> None:
        self.cfg = cfg
        headers = {}
        if cfg.access_token:
            headers["Authorization"] = f"Bearer {cfg.access_token}"
        if cfg.user_id:
            headers["New-Api-User"] = str(cfg.user_id)
        self._client = make_client(
            base_url=cfg.base_url,
            timeout=cfg.timeout,
            max_connections=cfg.max_connections,
            headers=headers,
        )

    async def aclose(self) -> None:
        await self._client.aclose()

    # ---------------- 内部 ----------------

    async def _get(self, path: str, params: dict[str, Any] | None = None) -> dict:
        try:
            resp = await self._client.get(path, params=params)
        except httpx.TimeoutException as e:
            raise UpstreamError(f"new-api {path} timeout: {e}") from e
        except httpx.HTTPError as e:
            raise UpstreamError(f"new-api {path} network error: {e}") from e

        if resp.status_code in (401, 403):
            raise AuthError(
                f"new-api auth failed (status={resp.status_code}) on {path}: "
                "check access_token + user_id (both headers required)"
            )
        if resp.status_code >= 400:
            raise UpstreamError(
                f"new-api {path} HTTP {resp.status_code}: {resp.text[:200]}"
            )

        try:
            payload = resp.json()
        except ValueError as e:
            raise UpstreamError(f"new-api {path} response not JSON: {e}") from e

        if not isinstance(payload, dict):
            raise UpstreamError(f"new-api {path} response not an object")
        if not payload.get("success", False):
            raise NewApiError(
                payload.get("message") or f"new-api {path} returned success=false",
                status_code=resp.status_code,
            )
        return payload

    # ---------------- 公开方法 ----------------

    async def get_channel(self, channel_id: int) -> dict:
        """获取 channel 详情。``channel_info`` 字段会被解析为 dict。"""
        payload = await self._get(f"/api/channel/{channel_id}")
        data = payload.get("data") or {}
        if not isinstance(data, dict):
            raise UpstreamError("new-api /api/channel/:id 'data' not an object")

        # channel_info 在数据库里通常以 JSON 字符串保存，反序列化后再返回
        ci = data.get("channel_info")
        if isinstance(ci, str) and ci.strip():
            try:
                data["channel_info"] = json.loads(ci)
            except json.JSONDecodeError:
                # 解析失败保留原值，由调用方决定如何处理
                pass
        elif ci is None:
            data["channel_info"] = {}
        return data

    async def get_log_stat(
        self,
        channel_id: int,
        log_type: int = LOG_TYPE_CONSUME,
    ) -> tuple[int, int]:
        """返回 (rpm, tpm)，固定为最近 60 秒。"""
        payload = await self._get(
            "/api/log/stat",
            params={"channel": channel_id, "type": log_type},
        )
        data = payload.get("data") or {}
        rpm = int(data.get("rpm") or 0)
        tpm = int(data.get("tpm") or 0)
        return rpm, tpm

    async def get_log_stat_multi(
        self,
        channel_ids: list[int],
        log_type: int = LOG_TYPE_CONSUME,
    ) -> tuple[int, int]:
        """并发查询多个 channel，返回求和后的 (rpm, tpm)。

        new-api 的 SumUsedQuota 不支持 channel IN 过滤（``model/log.go:411``），
        只能逐个调用。
        """
        if not channel_ids:
            return 0, 0
        results = await asyncio.gather(
            *(self.get_log_stat(cid, log_type) for cid in channel_ids),
            return_exceptions=False,
        )
        rpm = sum(r for r, _ in results)
        tpm = sum(t for _, t in results)
        return rpm, tpm


__all__ = ["NewApiClient", "NewApiError", "LOG_TYPE_CONSUME"]
