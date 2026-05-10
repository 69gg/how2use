"""配置加载：TOML 文件 + 环境变量覆盖

约定：
- 默认从仓库根目录的 ``config.toml`` 读取
- 环境变量前缀 ``HOW2USE_``，嵌套字段用 ``__`` 分隔
  例：HOW2USE_CLIENTS__NEW_API__ACCESS_TOKEN=xxx
"""
from __future__ import annotations

import os
import tomllib
from functools import lru_cache
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field, field_validator
from pydantic_settings import (
    BaseSettings,
    PydanticBaseSettingsSource,
    SettingsConfigDict,
)


class ServerConfig(BaseModel):
    host: str = "0.0.0.0"
    port: int = 8765
    api_key: str = ""
    cache_ttl_seconds: int = 5


class LoggingConfig(BaseModel):
    level: str = "INFO"


class NewApiClientConfig(BaseModel):
    base_url: str = "http://127.0.0.1:3000"
    access_token: str = ""
    user_id: int = 1
    timeout: float = 5.0
    max_connections: int = 20


class Grok2ApiClientConfig(BaseModel):
    base_url: str = "http://127.0.0.1:8000"
    app_key: str = ""
    timeout: float = 10.0
    max_connections: int = 10


class Gpt2ApiClientConfig(BaseModel):
    base_url: str = "http://127.0.0.1:18000"
    app_key: str = ""
    timeout: float = 10.0
    max_connections: int = 10


class ClientsConfig(BaseModel):
    new_api: NewApiClientConfig = Field(default_factory=NewApiClientConfig)
    grok2api: Grok2ApiClientConfig = Field(default_factory=Grok2ApiClientConfig)
    gpt2api: Gpt2ApiClientConfig = Field(default_factory=Gpt2ApiClientConfig)


class GrokProviderConfig(BaseModel):
    enabled: bool = True
    client: str = "grok2api"
    cooling_counts_as_used_concurrency: bool = True
    include_accounts: bool = True
    mask_tail_len: int = 8


class NimPoolConfig(BaseModel):
    name: str
    pool_size: int
    rpm_per_key: int = 40
    new_api_channel_ids: list[int] = Field(default_factory=list)
    probe_interval_seconds: int = 30

    @field_validator("new_api_channel_ids")
    @classmethod
    def _ensure_non_empty(cls, v: list[int]) -> list[int]:
        if not v:
            raise ValueError("new_api_channel_ids must contain at least one channel id")
        return v


class NimProviderConfig(BaseModel):
    enabled: bool = True
    client: str = "new_api"
    pools: list[NimPoolConfig] = Field(default_factory=list)


class Gpt2ApiProviderConfig(BaseModel):
    enabled: bool = True
    client: str = "gpt2api"
    cooling_counts_as_used_concurrency: bool = True
    include_accounts: bool = True
    mask_tail_len: int = 8


class ProvidersConfig(BaseModel):
    grok2api: GrokProviderConfig = Field(default_factory=GrokProviderConfig)
    nim: NimProviderConfig = Field(default_factory=NimProviderConfig)
    gpt2api: Gpt2ApiProviderConfig = Field(default_factory=Gpt2ApiProviderConfig)

    def iter_enabled(self) -> list[tuple[str, BaseModel]]:
        out: list[tuple[str, BaseModel]] = []
        for name, cfg in (
            ("grok2api", self.grok2api),
            ("nim", self.nim),
            ("gpt2api", self.gpt2api),
        ):
            if getattr(cfg, "enabled", False):
                out.append((name, cfg))
        return out


class AppConfig(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="HOW2USE_",
        env_nested_delimiter="__",
        case_sensitive=False,
        extra="ignore",
    )

    server: ServerConfig = Field(default_factory=ServerConfig)
    logging: LoggingConfig = Field(default_factory=LoggingConfig)
    clients: ClientsConfig = Field(default_factory=ClientsConfig)
    providers: ProvidersConfig = Field(default_factory=ProvidersConfig)

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        # 优先级：env > init kwargs (= TOML 文件) > secrets
        return env_settings, init_settings, file_secret_settings


def _load_toml(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    with path.open("rb") as f:
        return tomllib.load(f)


@lru_cache(maxsize=1)
def get_config(config_path: str | None = None) -> AppConfig:
    """加载配置（带 lru_cache，进程内单例）。

    优先级：环境变量 > TOML 文件 > 默认值
    """
    path_str = config_path or os.environ.get("HOW2USE_CONFIG_FILE", "config.toml")
    path = Path(path_str).resolve()
    file_data = _load_toml(path)
    return AppConfig(**file_data)


def reset_config_cache() -> None:
    get_config.cache_clear()


__all__ = [
    "AppConfig",
    "ServerConfig",
    "LoggingConfig",
    "ClientsConfig",
    "NewApiClientConfig",
    "Grok2ApiClientConfig",
    "Gpt2ApiClientConfig",
    "GrokProviderConfig",
    "NimPoolConfig",
    "NimProviderConfig",
    "Gpt2ApiProviderConfig",
    "ProvidersConfig",
    "get_config",
    "reset_config_cache",
]
