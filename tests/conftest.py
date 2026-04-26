"""pytest 公共 fixtures"""
from __future__ import annotations

import pytest

from app.core.config import (
    Grok2ApiClientConfig,
    GrokProviderConfig,
    NewApiClientConfig,
    NimPoolConfig,
    NimProviderConfig,
)


@pytest.fixture
def grok_client_cfg() -> Grok2ApiClientConfig:
    return Grok2ApiClientConfig(
        base_url="http://grok.test",
        app_key="test-key",
        timeout=2.0,
        max_connections=2,
    )


@pytest.fixture
def new_api_client_cfg() -> NewApiClientConfig:
    return NewApiClientConfig(
        base_url="http://newapi.test",
        access_token="acc-token",
        user_id=42,
        timeout=2.0,
        max_connections=2,
    )


@pytest.fixture
def grok_provider_cfg() -> GrokProviderConfig:
    return GrokProviderConfig(
        enabled=True,
        client="grok2api",
        cooling_counts_as_used_concurrency=True,
        include_accounts=True,
        mask_tail_len=4,
    )


@pytest.fixture
def nim_provider_cfg() -> NimProviderConfig:
    return NimProviderConfig(
        enabled=True,
        client="new_api",
        pools=[
            NimPoolConfig(
                name="default",
                pool_size=10,
                rpm_per_key=40,
                new_api_channel_ids=[42],
                probe_interval_seconds=30,
            ),
        ],
    )
