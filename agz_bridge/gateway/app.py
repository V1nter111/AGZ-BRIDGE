"""FastAPI Application factory and server configuration."""
import logging
from contextlib import asynccontextmanager
from typing import Any, Dict
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from agz_bridge.auth.pairing import get_pairing_manager
from agz_bridge.config.settings import get_settings
from agz_bridge.gateway.chat import router as chat_router
from agz_bridge.gateway.dashboard import router as dashboard_router
from agz_bridge.gateway.models import router as models_router
from agz_bridge.gateway.pairing_routes import router as pairing_router
from agz_bridge.monitoring.metrics import get_metrics
from agz_bridge.security.validator import NetworkSecurityMiddleware

logger = logging.getLogger("agz_bridge.gateway.app")


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    manager = get_pairing_manager()

    # Ensure an active pairing code exists on startup
    code = manager.get_active_pairing_code()
    if not code:
        code = manager.generate_pairing_code()

    logger.info("=" * 60)
    logger.info("AGZ BRIDGE HOST STARTED")
    logger.info(f"LAN Address:       http://{settings.lan_ip}:{settings.port}")
    if settings.tailscale_ip:
        logger.info(f"Tailscale Address: http://{settings.tailscale_ip}:{settings.port}")
    logger.info(f"Active Pairing Code: {code}")
    logger.info(f"Dashboard:         http://localhost:{settings.port}/dashboard")
    logger.info("=" * 60)

    yield

    logger.info("AGZ Bridge Host shutting down.")


def create_app() -> FastAPI:
    settings = get_settings()

    app = FastAPI(
        title="AGZ Bridge Host",
        description="High-performance bridge between Google Antigravity 2.0 CLI and Agent Zero",
        version="1.0.0",
        lifespan=lifespan,
    )

    # CORS
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Network Security (CIDR filtering)
    app.add_middleware(NetworkSecurityMiddleware)

    # Core Health & Metrics endpoints
    @app.get("/health")
    async def health_check() -> Dict[str, str]:
        return {"status": "healthy", "service": "agz-bridge-host"}

    @app.get("/api/metrics")
    async def get_metrics_endpoint() -> Dict[str, Any]:
        return get_metrics().get_summary()

    # Mount Routers
    app.include_router(dashboard_router)
    app.include_router(models_router)
    app.include_router(chat_router)
    app.include_router(pairing_router)

    return app
