"""GrokProvider：调 grok2api 自身的 admin API 拿账号池

并发模型：1 SSO token = 1 并发槽。
字段映射详见 plan：``/home/pyl/.claude/plans/enchanted-dazzling-avalanche.md``
"""
from __future__ import annotations

import time

from app.clients.grok2api_client import Grok2ApiClient
from app.core.config import GrokProviderConfig
from app.core.logger import logger
from app.providers import register
from app.providers.base import ProviderCapacity, ProviderError

def _now_ms() -> int:
    return int(time.time() * 1000)


@register("grok2api")
class GrokProvider:
    name: str = "grok2api"

    def __init__(self, cfg: GrokProviderConfig, client: Grok2ApiClient) -> None:
        self.cfg = cfg
        self.client = client

    async def aclose(self) -> None:
        # 客户端的生命周期由外层统一管理（main lifespan）
        pass

    async def fetch_capacity(self) -> list[ProviderCapacity]:
        try:
            pool_counts = await self.client.get_token_counts()
        except ProviderError as e:
            logger.warning("GrokProvider fetch failed: {}", e)
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
            out.append(self._build_pool_capacity_from_counts(pool_name, counts))
        out.sort(key=lambda c: c.pool_name or "")
        return out

    def _build_pool_capacity_from_counts(
        self, pool_name: str, counts: dict
    ) -> ProviderCapacity:
        total = int(counts.get("total") or 0)
        active = int(counts.get("active") or 0)
        cooling = int(counts.get("cooling") or 0)
        expired = int(counts.get("expired") or 0)
        disabled = int(counts.get("disabled") or 0)

        concurrency_total = active
        concurrency_used = cooling if self.cfg.cooling_counts_as_used_concurrency else 0
        concurrency_remaining = max(0, concurrency_total - concurrency_used)

        return ProviderCapacity(
            provider=self.name,
            pool_name=pool_name,
            accounts_total=total,
            accounts_active=active,
            accounts_cooling=cooling,
            accounts_expired=expired,
            accounts_disabled=disabled,
            concurrency_total=concurrency_total,
            concurrency_used=concurrency_used,
            concurrency_remaining=concurrency_remaining,
            rpm_limit=None,
            rpm_used=None,
            rpm_remaining=None,
            quota_remaining=float(int(counts.get("quota_total") or 0)),
            accounts=[],
            fetched_at=_now_ms(),
            healthy=True,
        )


__all__ = ["GrokProvider"]
