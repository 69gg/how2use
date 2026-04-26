"""NimProvider：基于 new-api 公开 API 推算 NIM 池容量

- 账号活性：从 new-api ``GET /api/channel/:id`` 的 ``status`` +
  ``channel_info.multi_key_status_list`` 计算（后台周期拉取，缓存到内存）
- 已用 RPM：``GET /api/log/stat?channel=&type=2``（实时调用，rpm 固定 60s 滑窗）
- 不直接调 NVIDIA NIM 上游

new-api channel.status 取值：
  1=enabled, 2=manually disabled, 3=auto disabled
multi_key_status_list 取值：
  0=enabled, 其他=disabled（保守处理：非 0 都视为不可用）
"""
from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field

from app.clients.new_api_client import NewApiClient
from app.core.config import NimPoolConfig, NimProviderConfig
from app.core.logger import logger
from app.providers import register
from app.providers.base import AccountSlot, ProviderCapacity, ProviderError

CHANNEL_STATUS_ENABLED = 1
KEY_STATUS_ENABLED = 0


def _now_ms() -> int:
    return int(time.time() * 1000)


@dataclass
class _ChannelState:
    channel_id: int
    status: int = 0
    is_multi_key: bool = False
    multi_key_size: int = 0
    multi_key_status_list: dict[int, int] = field(default_factory=dict)
    error: str | None = None
    fetched_at: int = 0

    @property
    def enabled_key_count(self) -> int | None:
        if not self.is_multi_key or not self.multi_key_status_list:
            return None
        return sum(
            1 for v in self.multi_key_status_list.values() if v == KEY_STATUS_ENABLED
        )


@register("nim")
class NimProvider:
    name: str = "nim"

    def __init__(self, cfg: NimProviderConfig, client: NewApiClient) -> None:
        self.cfg = cfg
        self.client = client
        self._channel_state: dict[int, _ChannelState] = {}
        self._probe_tasks: list[asyncio.Task] = []

    async def start(self) -> None:
        await self._probe_all_once()
        for pool in self.cfg.pools:
            task = asyncio.create_task(
                self._probe_loop(pool), name=f"nim-probe-{pool.name}"
            )
            self._probe_tasks.append(task)

    async def aclose(self) -> None:
        for t in self._probe_tasks:
            t.cancel()
        for t in self._probe_tasks:
            try:
                await t
            except (asyncio.CancelledError, Exception):  # noqa: BLE001
                pass
        self._probe_tasks.clear()

    async def _probe_all_once(self) -> None:
        all_ids = {cid for pool in self.cfg.pools for cid in pool.new_api_channel_ids}
        await asyncio.gather(*(self._probe_channel(cid) for cid in all_ids))

    async def _probe_loop(self, pool: NimPoolConfig) -> None:
        interval = max(5, pool.probe_interval_seconds)
        while True:
            try:
                await asyncio.sleep(interval)
                await asyncio.gather(
                    *(self._probe_channel(cid) for cid in pool.new_api_channel_ids)
                )
            except asyncio.CancelledError:
                raise
            except Exception as e:  # noqa: BLE001
                logger.warning(
                    "NimProvider probe loop error (pool={}): {}", pool.name, e
                )

    async def _probe_channel(self, channel_id: int) -> None:
        try:
            data = await self.client.get_channel(channel_id)
        except ProviderError as e:
            self._channel_state[channel_id] = _ChannelState(
                channel_id=channel_id, error=str(e), fetched_at=_now_ms()
            )
            logger.debug("probe channel {} failed: {}", channel_id, e)
            return

        ci = data.get("channel_info") or {}
        if not isinstance(ci, dict):
            ci = {}

        raw_list = ci.get("multi_key_status_list") or {}
        normalized: dict[int, int] = {}
        if isinstance(raw_list, dict):
            for k, v in raw_list.items():
                try:
                    normalized[int(k)] = int(v)
                except (TypeError, ValueError):
                    continue

        self._channel_state[channel_id] = _ChannelState(
            channel_id=channel_id,
            status=int(data.get("status") or 0),
            is_multi_key=bool(ci.get("is_multi_key")),
            multi_key_size=int(ci.get("multi_key_size") or 0),
            multi_key_status_list=normalized,
            error=None,
            fetched_at=_now_ms(),
        )

    async def fetch_capacity(self) -> list[ProviderCapacity]:
        out: list[ProviderCapacity] = []
        for pool in self.cfg.pools:
            out.append(await self._build_pool_capacity(pool))
        return out

    async def _build_pool_capacity(self, pool: NimPoolConfig) -> ProviderCapacity:
        states = [self._channel_state.get(cid) for cid in pool.new_api_channel_ids]

        rpm_used: int | None
        rpm_error: str | None = None
        try:
            rpm_used, _ = await self.client.get_log_stat_multi(pool.new_api_channel_ids)
        except ProviderError as e:
            rpm_used = None
            rpm_error = str(e)
            logger.warning(
                "NimProvider get_log_stat_multi failed (pool={}): {}", pool.name, e
            )

        accounts_active = self._calc_active(pool, states)
        accounts_total = pool.pool_size
        rpm_limit = accounts_active * pool.rpm_per_key
        rpm_remaining: int | None
        if rpm_used is None:
            rpm_remaining = None
        else:
            rpm_remaining = max(0, rpm_limit - rpm_used)

        accounts = self._build_account_slots(pool, states)

        probe_errors = [s.error for s in states if s and s.error]
        healthy = rpm_error is None and not probe_errors
        if rpm_error and probe_errors:
            error_msg: str | None = f"rpm: {rpm_error}; probe: {'; '.join(probe_errors)}"
        elif rpm_error:
            error_msg = rpm_error
        elif probe_errors:
            error_msg = "; ".join(probe_errors)
        else:
            error_msg = None

        return ProviderCapacity(
            provider=self.name,
            pool_name=pool.name,
            accounts_total=accounts_total,
            accounts_active=accounts_active,
            accounts_disabled=max(0, accounts_total - accounts_active),
            concurrency_total=0,
            concurrency_used=0,
            concurrency_remaining=0,
            rpm_limit=rpm_limit,
            rpm_used=rpm_used,
            rpm_remaining=rpm_remaining,
            quota_remaining=None,
            accounts=accounts,
            fetched_at=_now_ms(),
            healthy=healthy,
            error=error_msg,
        )

    @staticmethod
    def _calc_active(
        pool: NimPoolConfig, states: list[_ChannelState | None]
    ) -> int:
        if not states or any(s is None for s in states):
            return pool.pool_size

        if not any(s.status == CHANNEL_STATUS_ENABLED for s in states):  # type: ignore[union-attr]
            return 0

        precise: int = 0
        precise_known = False
        fallback: int = 0
        for s in states:
            assert s is not None
            if s.status != CHANNEL_STATUS_ENABLED:
                continue
            ec = s.enabled_key_count
            if ec is not None:
                precise += ec
                precise_known = True
            else:
                fallback += pool.pool_size

        result = precise if precise_known else fallback
        return min(pool.pool_size, max(0, result))

    @staticmethod
    def _build_account_slots(
        pool: NimPoolConfig, states: list[_ChannelState | None]
    ) -> list[AccountSlot]:
        slots: list[AccountSlot] = []
        for s in states:
            if s is None or not s.is_multi_key or not s.multi_key_status_list:
                continue
            for key_index, key_status in sorted(s.multi_key_status_list.items()):
                slots.append(
                    AccountSlot(
                        id=f"ch{s.channel_id}-k{key_index}",
                        status="active" if key_status == KEY_STATUS_ENABLED else "disabled",
                        rpm_limit=pool.rpm_per_key,
                    )
                )
        return slots


__all__ = ["NimProvider"]
