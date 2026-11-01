"""Endpoints for pairing, status verification, and device management."""
import logging
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel, Field

from agz_bridge.auth.pairing import get_pairing_manager
from agz_bridge.config.settings import get_settings

logger = logging.getLogger("agz_bridge.gateway.pairing_routes")
router = APIRouter(prefix="/api/pair", tags=["Pairing"])


class PairRequest(BaseModel):
    pairing_code: str = Field(..., description="The one-time pairing code shown on Host")
    worker_name: str = Field(default="worker-pc", description="Human-readable name of worker")
    os_info: str = Field(default="Windows", description="OS information of worker")


class PairResponse(BaseModel):
    status: str
    message: str
    token: Optional[str] = None
    host_url: str
    default_model: str
    available_models: List[str]


class RevokeRequest(BaseModel):
    worker_id: str


@router.get("/status")
async def pairing_status() -> Dict[str, Any]:
    """Public check endpoint for Worker installer to probe connectivity."""
    settings = get_settings()
    manager = get_pairing_manager()
    active_code = manager.get_active_pairing_code()
    return {
        "status": "online",
        "service": "AGZ Bridge Host",
        "has_active_pairing_code": active_code is not None,
        "lan_ip": settings.lan_ip,
        "tailscale_ip": settings.tailscale_ip,
        "default_model": settings.default_model,
    }


@router.post("", response_model=PairResponse)
async def pair_worker(req: PairRequest, request: Request) -> PairResponse:
    """Pair a new worker device using a one-time pairing code."""
    manager = get_pairing_manager()
    settings = get_settings()
    client_ip = request.client.host if request.client else "unknown"

    success, msg, token = manager.validate_and_consume_code(
        code=req.pairing_code,
        worker_name=req.worker_name,
        os_info=req.os_info,
        client_ip=client_ip
    )

    if not success:
        logger.warning(f"Failed pairing attempt from {client_ip}: {msg}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=msg
        )

    return PairResponse(
        status="paired",
        message="Successfully paired with AGZ Bridge Host.",
        token=token,
        host_url=settings.primary_url,
        default_model=settings.default_model,
        available_models=settings.available_models,
    )


@router.post("/generate")
async def generate_new_code(request: Request) -> Dict[str, Any]:
    """Generate a new pairing code (callable locally or from dashboard)."""
    # Allow local or authorized calls
    client_ip = request.client.host if request.client else "unknown"
    manager = get_pairing_manager()
    settings = get_settings()

    code = manager.generate_pairing_code()
    return {
        "pairing_code": code,
        "expires_in_seconds": settings.pairing_code_lifetime_seconds,
        "host_url": settings.primary_url,
    }


@router.post("/revoke")
async def revoke_worker_device(req: RevokeRequest) -> Dict[str, Any]:
    """Revoke a worker by ID."""
    manager = get_pairing_manager()
    success = manager.revoke_worker(req.worker_id)
    if not success:
        raise HTTPException(status_code=404, detail="Worker ID not found.")
    return {"status": "revoked", "worker_id": req.worker_id}


@router.get("/workers")
async def list_workers() -> List[Dict[str, Any]]:
    """List paired workers for dashboard monitoring."""
    manager = get_pairing_manager()
    workers = manager.list_workers()
    return [w.model_dump(exclude={"token_hash"}) for w in workers]
