"""OpenAI-compatible /v1/models endpoint."""
import time
from typing import Any, Dict, List
from fastapi import APIRouter, Depends

from agz_bridge.antigravity_adapter.cli_runner import get_cli
from agz_bridge.auth.pairing import PairedWorker
from agz_bridge.auth.security import get_token_security

router = APIRouter(prefix="/v1", tags=["Models"])


@router.get("/models")
async def list_models(
    worker: PairedWorker = Depends(get_token_security().authenticate_request)
) -> Dict[str, Any]:
    """List available models supported by Antigravity CLI in OpenAI format."""
    cli = get_cli()
    available = await cli.list_models()
    created_time = int(time.time())

    models_data: List[Dict[str, Any]] = []
    for m in available:
        model_id = m.get("id")
        models_data.append({
            "id": model_id,
            "object": "model",
            "created": created_time,
            "owned_by": "google-antigravity",
            "permission": [],
            "root": model_id,
            "parent": None,
        })

    return {
        "object": "list",
        "data": models_data,
    }
