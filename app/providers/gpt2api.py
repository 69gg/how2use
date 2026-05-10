"""Gpt2ApiProvider：调 gpt2api 自身的 admin API 拿 token 池

并发模型：1 token = 1 并发槽。
"""
from __future__ import annotations

import time
from typing import Iterable

from app.clients.gpt2api_client import Gpt2ApiClient
from app.core.config import Gpt2ApiProviderConfig
from app.core.logger import logger
from app.providers import register
from app.providers.base import AccountSlot, ProviderCapacity, ProviderError

STATUS_ACTIVE = "active"
STATUS_COOLING = "cooling"
STATUS_EXPIRED = "expired"
STATUS_DISABLED = "disabled"


def _now_ms() -> int:
    return int(time.time() * 1000)


def _mask(token: str, tail: int) -> str:
    if not token:
        return ""
    tail = max(1, tail)
    if len(token) <= tail:
        return token
    return token[-tail:]


@register("gpt2api")
class Gpt2ApiProvider:
    name: str = "gpt2api"

    def __init__(self, cfg: Gpt2ApiProviderConfig, client: Gpt2ApiClient) -> None:
        self.cfg = cfg
        self.client = client

    async def aclose(self) -> None:
        pass

    async def fetch_capacity(self) -> list[ProviderCapacity]:
        try:
            pools = await self.client.get_tokens()
        except ProviderError as e:
            logger.warning("Gpt2ApiProvider fetch failed: {}", e)
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
        for pool_name, tokens in pools.items():
            out.append(self._build_pool_capacity(pool_name, tokens or []))
        out.sort(key=lambda c: c.pool_name or "")
        return out

    def _build_pool_capacity(
        self, pool_name: str, tokens: Iterable[dict]
    ) -> ProviderCapacity:
        token_list = list(tokens)
        active = cooling = expired = disabled = 0
        accounts: list[AccountSlot] = []

        for t in token_list:
            status = str(t.get("status") or "").lower()
            if status == STATUS_ACTIVE:
                active += 1
            elif status == STATUS_COOLING:
                cooling += 1
            elif status == STATUS_EXPIRED:
                expired += 1
            elif status == STATUS_DISABLED:
                disabled += 1

            if self.cfg.include_accounts:
                accounts.append(
                    AccountSlot(
                        id=_mask(str(t.get("token") or ""), self.cfg.mask_tail_len),
                        status=status or "unknown",
                        use_count=int(t.get("use_count") or 0),
                        fail_count=int(t.get("fail_count") or 0),
                        last_used_at=t.get("last_used_at"),
                    )
                )

        concurrency_total = active
        concurrency_used = cooling if self.cfg.cooling_counts_as_used_concurrency else 0
        concurrency_remaining = max(0, concurrency_total - concurrency_used)

        return ProviderCapacity(
            provider=self.name,
            pool_name=pool_name,
            accounts_total=len(token_list),
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
            quota_remaining=None,
            accounts=accounts,
            fetched_at=_now_ms(),
            healthy=True,
        )


__all__ = ["Gpt2ApiProvider"]