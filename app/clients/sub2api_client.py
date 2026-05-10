"""sub2api HTTP 客户端

sub2api 是 Go 项目，Admin API 使用 ``x-api-key`` 头鉴权。
数据通过两个现有端点获取：

- ``GET /api/v1/admin/groups/all`` → 账号计数 {account_count, active_account_count, rate_limited_account_count}
- ``GET /api/v1/admin/groups/capacity-summary`` → 实时并发 {concurrency_max, concurrency_used}

两个响应合并后返回给 Provider。
"""
from __future__ import annotations

import httpx

from app.core.config import Sub2ApiClientConfig
from app.core.http_client import make_client
from app.providers.base import AuthError, UpstreamError


class Sub2ApiClient:
    """sub2api 管理接口客户端"""

    def __init__(self, cfg: Sub2ApiClientConfig) -> None:
        self.cfg = cfg
        self._client = make_client(
            base_url=cfg.base_url,
            timeout=cfg.timeout,
            max_connections=cfg.max_connections,
            headers={"x-api-key": cfg.admin_key} if cfg.admin_key else {},
        )

    async def aclose(self) -> None:
        await self._client.aclose()

    async def health(self) -> bool:
        try:
            resp = await self._client.get("/health")
        except httpx.HTTPError as e:
            raise UpstreamError(f"sub2api /health failed: {e}") from e
        return resp.status_code == 200

    async def _get_groups(self) -> list[dict]:
        """获取所有 active group 的账号计数。"""
        try:
            resp = await self._client.get("/api/v1/admin/groups/all")
        except httpx.TimeoutException as e:
            raise UpstreamError(f"sub2api /groups/all timeout: {e}") from e
        except httpx.HTTPError as e:
            raise UpstreamError(f"sub2api /groups/all network error: {e}") from e

        if resp.status_code in (401, 403):
            raise AuthError(
                f"sub2api auth failed (status={resp.status_code}): check admin_key"
            )
        if resp.status_code >= 400:
            raise UpstreamError(
                f"sub2api /groups/all HTTP {resp.status_code}: {resp.text[:200]}"
            )

        try:
            payload = resp.json()
        except ValueError as e:
            raise UpstreamError(f"sub2api response not JSON: {e}") from e

        groups: list[dict] = payload.get("data") or []
        if not isinstance(groups, list):
            raise UpstreamError(
                f"sub2api /groups/all 'data' not a list: {type(groups).__name__}"
            )
        return groups

    async def _get_capacity_summary(self) -> list[dict]:
        """获取所有 group 的实时并发容量。"""
        try:
            resp = await self._client.get("/api/v1/admin/groups/capacity-summary")
        except httpx.TimeoutException as e:
            raise UpstreamError(f"sub2api /capacity-summary timeout: {e}") from e
        except httpx.HTTPError as e:
            raise UpstreamError(f"sub2api /capacity-summary network error: {e}") from e

        if resp.status_code in (401, 403):
            raise AuthError(
                f"sub2api auth failed (status={resp.status_code}): check admin_key"
            )
        if resp.status_code >= 400:
            raise UpstreamError(
                f"sub2api /capacity-summary HTTP {resp.status_code}: {resp.text[:200]}"
            )

        try:
            payload = resp.json()
        except ValueError as e:
            raise UpstreamError(f"sub2api response not JSON: {e}") from e

        caps: list[dict] = payload.get("data") or []
        if not isinstance(caps, list):
            raise UpstreamError(
                f"sub2api /capacity-summary 'data' not a list: {type(caps).__name__}"
            )
        return caps

    async def get_token_counts(self) -> dict[str, dict]:
        """合并 groups/all 和 capacity-summary 数据。

        返回 ``{group_name: {total, active, cooling, concurrency_max, concurrency_used}}``
        """
        groups = await self._get_groups()
        caps = await self._get_capacity_summary()

        cap_map: dict[int, dict] = {}
        for c in caps:
            cap_map[int(c.get("group_id") or 0)] = c

        result: dict[str, dict] = {}
        for g in groups:
            gid = int(g.get("id") or 0)
            name = str(g.get("name") or gid)
            cap = cap_map.get(gid, {})

            result[name] = {
                "total": int(g.get("account_count") or 0),
                "active": int(g.get("active_account_count") or 0),
                "cooling": int(g.get("rate_limited_account_count") or 0),
                "concurrency_total": int(cap.get("concurrency_max") or 0),
                "concurrency_used": int(cap.get("concurrency_used") or 0),
                # 以下子段 sub2api 现有 API 无法获取，始终为 0
                "disabled": 0,
                "expired": 0,
            }
        return result


__all__ = ["Sub2ApiClient"]