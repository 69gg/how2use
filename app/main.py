"""FastAPI 入口"""
from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles

from app.api.routes import router as api_router
from app.cache import CapacityCache
from app.clients.grok2api_client import Grok2ApiClient
from app.clients.new_api_client import NewApiClient
from app.core.config import get_config
from app.core.logger import logger, setup_logger
from app.providers import build_providers


@asynccontextmanager
async def lifespan(app: FastAPI):
    cfg = get_config()
    setup_logger(cfg.logging.level)
    logger.info("how2use starting on {}:{}", cfg.server.host, cfg.server.port)

    # 客户端实例化（按需）
    clients: dict[str, object] = {}
    enabled = cfg.providers.iter_enabled()
    needs_grok = any(getattr(c, "client", None) == "grok2api" for _, c in enabled)
    needs_new_api = any(getattr(c, "client", None) == "new_api" for _, c in enabled)

    grok_client: Grok2ApiClient | None = None
    new_api_client: NewApiClient | None = None
    if needs_grok:
        grok_client = Grok2ApiClient(cfg.clients.grok2api)
        clients["grok2api"] = grok_client
    if needs_new_api:
        new_api_client = NewApiClient(cfg.clients.new_api)
        clients["new_api"] = new_api_client

    providers = build_providers(enabled, clients)
    app.state.providers = {p.name: p for p in providers}
    app.state.cache = CapacityCache(ttl_seconds=cfg.server.cache_ttl_seconds)
    app.state.clients = clients

    # 启动需要后台任务的 provider
    for p in providers:
        start = getattr(p, "start", None)
        if start is not None:
            try:
                await start()
            except Exception as e:  # noqa: BLE001
                logger.warning("provider {} start() failed: {}", p.name, e)

    logger.info(
        "providers: {} | clients: {}",
        list(app.state.providers.keys()),
        list(clients.keys()),
    )

    try:
        yield
    finally:
        for p in providers:
            try:
                await p.aclose()
            except Exception as e:  # noqa: BLE001
                logger.warning("provider {} aclose failed: {}", p.name, e)
        if grok_client is not None:
            await grok_client.aclose()
        if new_api_client is not None:
            await new_api_client.aclose()
        logger.info("how2use stopped")


def create_app() -> FastAPI:
    app = FastAPI(title="how2use", version="0.1.0", lifespan=lifespan)
    app.include_router(api_router)

    # 挂载静态文件
    static_dir = Path(__file__).parent.parent / "static"
    if static_dir.exists():
        app.mount("/static", StaticFiles(directory=static_dir), name="static")

    # 根路由重定向到静态文件
    @app.get("/", include_in_schema=False)
    async def root():
        return RedirectResponse(url="/static/index.html")

    return app


app = create_app()


if __name__ == "__main__":
    import uvicorn

    cfg = get_config()
    uvicorn.run(
        "app.main:app",
        host=cfg.server.host,
        port=cfg.server.port,
        reload=False,
    )
