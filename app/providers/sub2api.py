"""Sub2ApiProvider：调用 sub2api Admin API 获取各 group 的账号与并发容量

并发模型：group 维度的 concurrency_max/concurrency_used 来自 sub2api 实时 Redis 数据。
"""
from __future__ import annotations

import time

from app.clients.sub2api_client import Sub2ApiClient
from app.core.config import Sub2ApiProviderConfig
from app.core.logger import logger
from app.providers import register
from app.providers.base import ProviderCapacity, ProviderError


def _now_ms() -> int:
    return int(time.time() * 1000)


@register("sub2api")
class Sub2ApiProvider:
    name: str = "sub2api"

    def __init__(self, cfg: Sub2ApiProviderConfig, client: Sub2ApiClient) -> None:
        self.cfg = cfg
        self.client = client

    async def aclose(self) -> None:
        pass

    async def fetch_capacity(self) -> list[ProviderCapacity]:
        try:
            pool_counts = await self.client.get_token_counts()
        except ProviderError as e:
            logger.warning("Sub2ApiProvider fetch failed: {}", e)
            return [
                ProviderCapacity(
                    provider=self.name,
                    pool_name=None,
                    fetched_at=_now_ms(),
                    healthy=False,
                    error=str(e),
                )
            ]

        out: list[ProviderCapacity] = []
        for pool_name, counts in pool_counts.items():
            out.append(self._build_pool_capacity(pool_name, counts))
        out.sort(key=lambda c: c.pool_name or "")
        return out

    def _build_pool_capacity(
        self, pool_name: str, counts: dict
    ) -> ProviderCapacity:
        total = int(counts.get("total") or 0)
        active = int(counts.get("active") or 0)
        cooling = int(counts.get("cooling") or 0)
        # sub2api 现有 API 无法获取 disabled/expired，始终传 0

        concurrency_total = int(counts.get("concurrency_total") or 0)
        concurrency_used = int(counts.get("concurrency_used") or 0)
        concurrency_remaining = max(0, concurrency_total - concurrency_used)

        return ProviderCapacity(
            provider=self.name,
            pool_name=pool_name,
            accounts_total=total,
            accounts_active=active,
            accounts_cooling=cooling,
            accounts_expired=0,
            accounts_disabled=0,
            concurrency_total=concurrency_total,
            concurrency_used=concurrency_used,
            concurrency_remaining=concurrency_remaining,
            rpm_limit=None,
            rpm_used=None,
            rpm_remaining=None,
            quota_remaining=None,
            accounts=[],
            fetched_at=_now_ms(),
            healthy=True,
        )


__all__ = ["Sub2ApiProvider"]