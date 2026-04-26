# how2use

上游 LLM provider 容量 / 额度 / RPM 统一查询服务。

下游接 [new-api](https://github.com/QuantumNous/new-api) 作为统一中转网关，本服务对外暴露统一接口，回答"某 provider 此刻还能承载多少并发 / 还剩多少 RPM / 还剩多少额度"。

## 已支持 Provider

| Provider | 数据来源 | 并发模型 | RPM | 剩余额度 |
|---|---|---|---|---|
| `grok2api` | 调 grok2api 自身 `GET /v1/admin/tokens` | 1 SSO token = 1 槽位 | — | 池中 active token 的 quota 之和 |
| `nim` | new-api 公开 API（`/api/channel/:id` + `/api/log/stat`） | — | `accounts_active * 40`（可配） | — |

## 快速开始

```bash
# 1. 装依赖
uv sync                         # 或 pip install -e .

# 2. 复制示例配置并编辑（最少改三处见下）
cp config.toml.example config.toml
vim config.toml

# 3. 启动
uv run uvicorn app.main:app --host 0.0.0.0 --port 8765
# 或：python -m app.main
```

## 必填配置

编辑 `config.toml`：

1. **grok2api 客户端**：`[clients.grok2api] app_key` —— 与 grok2api 的 `SERVER_APP_KEY` 一致
2. **new-api 客户端**：`[clients.new_api] access_token` + `user_id` —— 在 new-api 后台"个人设置"生成 Token，并填入对应用户 ID（admin 通常为 1）
3. **NIM 池**：`[[providers.nim.pools]] new_api_channel_ids = [...]` —— 该池在 new-api 中对应的 channel id 列表

所有字段都可被环境变量覆盖（嵌套用 `__`）：

```bash
HOW2USE_CLIENTS__GROK2API__APP_KEY=xxx
HOW2USE_CLIENTS__NEW_API__ACCESS_TOKEN=xxx
HOW2USE_CLIENTS__NEW_API__USER_ID=1
HOW2USE_SERVER__API_KEY=xxx          # 可选：服务自身 X-API-Key 鉴权
```

## 多 NIM 池配置

每个池对应一组 new-api channel：

```toml
[[providers.nim.pools]]
name = "default"
pool_size = 10                  # 该池 key 数量
rpm_per_key = 40                # 单 key RPM 限速
new_api_channel_ids = [42]      # 关联到 new-api 的 channel id
probe_interval_seconds = 2      # 轮询 used_quota 的周期（秒），用于实时 RPM 融合

[[providers.nim.pools]]
name = "premium"
pool_size = 5
rpm_per_key = 40
new_api_channel_ids = [55, 56]  # 多 channel 聚合
probe_interval_seconds = 2
```

## API

```
GET  /health                           健康检查
GET  /providers                        启用的 provider 列表
GET  /capacity                         全部 provider 的全部 pool 容量
GET  /capacity/{provider}              单 provider 全部 pool
GET  /capacity/{provider}/{pool}       单 pool 详情
POST /refresh                          强制刷新缓存（X-API-Key 鉴权）
POST /refresh/{provider}               仅刷新某 provider
```

响应示例（节选）：

```json
{
  "fetched_at": 1735000000000,
  "providers": [
    {
      "provider": "grok2api",
      "pool_name": "ssoBasic",
      "accounts_total": 5,
      "accounts_active": 2,
      "accounts_cooling": 1,
      "concurrency_total": 2,
      "concurrency_used": 1,
      "concurrency_remaining": 1,
      "quota_remaining": 120.0,
      "healthy": true
    },
    {
      "provider": "nim",
      "pool_name": "default",
      "accounts_total": 10,
      "accounts_active": 7,
      "rpm_limit": 280,
      "rpm_used": 15,
      "rpm_remaining": 265,
      "healthy": true
    }
  ]
}
```

## 扩展新 Provider

1. 在 `app/providers/` 新建 `myprovider.py`
2. 实现 `fetch_capacity() -> list[ProviderCapacity]` 方法
3. 用 `@register("myprovider")` 装饰器登记
4. 在 `app/core/config.py` 加配置模型，`config.toml` 加 `[providers.myprovider]`

参考现有的 `grok2api.py` 与 `nim.py`。

## 测试

```bash
uv run pytest -q
```

## Docker

```bash
docker build -t how2use .

# 复制示例配置并编辑
cp config.toml.example config.toml
vim config.toml

# 运行（挂载配置文件）
docker run -p 8765:8765 \
  -v $(pwd)/config.toml:/app/config.toml \
  how2use
```

## 已知限制

- **NIM 单 key RPM 不可拆分**：new-api 的 `SumUsedQuota` 不支持按 key_index 过滤，目前只能聚合到 channel 维度。
- **grok2api 并发是估算**：以 `cooling` 计数近似已占并发；池本身不暴露瞬时 in-flight 计数。
- **多 channel 聚合**：同一 pool 跨多 channel 时 `rpm_used` 是合计值。
