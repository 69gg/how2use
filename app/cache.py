"""TTL 缓存 + per-key 反击穿锁

用法：
    cache = CapacityCache(ttl_seconds=5)
    result = await cache.get_or_fetch(("grok2api", None), fetch_coro_fn)
"""
from __future__ import annotations

import asyncio
from typing import Awaitable, Callable, Hashable, TypeVar

from cachetools import TTLCache

T = TypeVar("T")


class CapacityCache:
    def __init__(self, ttl_seconds: int, maxsize: int = 256) -> None:
        self._ttl = max(1, ttl_seconds)
        self._cache: TTLCache[Hashable, object] = TTLCache(maxsize=maxsize, ttl=self._ttl)
        self._locks: dict[Hashable, asyncio.Lock] = {}
        self._global_lock = asyncio.Lock()

    async def _lock_for(self, key: Hashable) -> asyncio.Lock:
        async with self._global_lock:
            lock = self._locks.get(key)
            if lock is None:
                lock = asyncio.Lock()
                self._locks[key] = lock
            return lock

    async def get_or_fetch(
        self,
        key: Hashable,
        fetcher: Callable[[], Awaitable[T]],
    ) -> T:
        cached = self._cache.get(key)
        if cached is not None:
            return cached  # type: ignore[return-value]

        lock = await self._lock_for(key)
        async with lock:
            cached = self._cache.get(key)
            if cached is not None:
                return cached  # type: ignore[return-value]
            value = await fetcher()
            self._cache[key] = value
            return value

    def invalidate_all(self) -> None:
        self._cache.clear()

    def invalidate_prefix(self, prefix: str) -> None:
        """删除 key 第一段等于 prefix 的所有缓存（key 是 tuple）。"""
        to_drop = [k for k in list(self._cache.keys()) if isinstance(k, tuple) and k and k[0] == prefix]
        for k in to_drop:
            self._cache.pop(k, None)


__all__ = ["CapacityCache"]
