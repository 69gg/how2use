"""Provider 注册表与工厂"""
from __future__ import annotations

from typing import Any, Callable

from .base import UpstreamProvider

PROVIDER_REGISTRY: dict[str, type[UpstreamProvider]] = {}


def register(name: str) -> Callable[[type[UpstreamProvider]], type[UpstreamProvider]]:
    """装饰器：把一个 Provider 类登记到全局注册表。"""

    def deco(cls: type[UpstreamProvider]) -> type[UpstreamProvider]:
        if name in PROVIDER_REGISTRY:
            raise RuntimeError(f"Provider '{name}' already registered")
        PROVIDER_REGISTRY[name] = cls
        return cls

    return deco


def build_providers(
    provider_configs: list[tuple[str, Any]],
    clients: dict[str, Any],
) -> list[UpstreamProvider]:
    """按配置实例化所有启用的 provider。

    Args:
        provider_configs: ``[(provider_name, provider_cfg), ...]``
        clients: ``{client_name: client_instance}``
    """
    # 触发子模块的注册装饰器
    from . import grok2api as _grok  # noqa: F401
    from . import nim as _nim  # noqa: F401
    from . import gpt2api as _gpt2api  # noqa: F401

    out: list[UpstreamProvider] = []
    for name, cfg in provider_configs:
        cls = PROVIDER_REGISTRY.get(name)
        if cls is None:
            raise RuntimeError(f"Provider '{name}' not registered")
        client_name = getattr(cfg, "client", name)
        client = clients.get(client_name)
        if client is None:
            raise RuntimeError(
                f"Provider '{name}' references unknown client '{client_name}'"
            )
        out.append(cls(cfg, client))
    return out


__all__ = ["PROVIDER_REGISTRY", "register", "build_providers"]
