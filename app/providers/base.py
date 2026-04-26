"""Provider 抽象 + 统一数据模型

所有 Provider 都返回一组 ``ProviderCapacity``（一个 provider 可有多个 pool）。
"""
from __future__ import annotations

from typing import Optional, Protocol, runtime_checkable

from pydantic import BaseModel, Field


# ================ 统一异常 ================

class ProviderError(Exception):
    """Provider 层基类异常"""


class UpstreamError(ProviderError):
    """上游服务返回错误（5xx / 网络 / 协议异常）"""


class AuthError(ProviderError):
    """鉴权失败（401 / 403 / token 配错）"""


# ================ 数据模型 ================

class AccountSlot(BaseModel):
    """单个账号 / Key 的容量明细"""

    id: str
    status: str = "unknown"  # active | cooling | expired | disabled | unknown
    rpm_limit: Optional[int] = None
    quota_total: Optional[int] = None
    quota_remaining: Optional[float] = None
    consumed: Optional[int] = None
    use_count: Optional[int] = None
    fail_count: Optional[int] = None
    tags: list[str] = Field(default_factory=list)
    last_used_at: Optional[int] = None  # ms


class ProviderCapacity(BaseModel):
    """某 provider 某 pool 的容量快照"""

    provider: str
    pool_name: Optional[str] = None

    # 账号维度
    accounts_total: int = 0
    accounts_active: int = 0
    accounts_cooling: int = 0
    accounts_expired: int = 0
    accounts_disabled: int = 0

    # 并发维度（grok：1 token = 1 槽；nim：留 0）
    concurrency_total: int = 0
    concurrency_used: int = 0
    concurrency_remaining: int = 0

    # RPM 维度
    rpm_limit: Optional[int] = None
    rpm_used: Optional[int] = None
    rpm_remaining: Optional[int] = None

    # 额度（grok 有，nim 通常 None）
    quota_remaining: Optional[float] = None

    accounts: list[AccountSlot] = Field(default_factory=list)

    fetched_at: int = 0  # ms
    healthy: bool = True
    error: Optional[str] = None


# ================ Protocol ================

@runtime_checkable
class UpstreamProvider(Protocol):
    """所有 provider 实现的统一接口"""

    name: str

    async def fetch_capacity(self) -> list[ProviderCapacity]: ...

    async def aclose(self) -> None: ...


__all__ = [
    "ProviderError",
    "UpstreamError",
    "AuthError",
    "AccountSlot",
    "ProviderCapacity",
    "UpstreamProvider",
]
