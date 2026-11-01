"""OpenAI-compatible /v1/chat/completions endpoint."""
import asyncio
import json
import logging
import time
import uuid
from typing import Any, AsyncIterator, Dict, List, Optional
from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, Field

from agz_bridge.antigravity_adapter.cli_runner import AntigravityCLIError, get_cli
from agz_bridge.antigravity_adapter.prompt_builder import PromptBuilder
from agz_bridge.antigravity_adapter.stream_parser import StreamParser
from agz_bridge.auth.pairing import PairedWorker
from agz_bridge.auth.security import get_token_security
from agz_bridge.config.settings import get_settings
from agz_bridge.monitoring.metrics import get_metrics
from agz_bridge.session_manager.manager import get_session_manager
from agz_bridge.tool_call_adapter.adapter import ToolCallAdapter

logger = logging.getLogger("agz_bridge.gateway.chat")
router = APIRouter(prefix="/v1", tags=["Chat"])


class ChatCompletionRequest(BaseModel):
    model: Optional[str] = None
    messages: List[Dict[str, Any]] = Field(..., min_length=1)
    stream: Optional[bool] = False
    tools: Optional[List[Dict[str, Any]]] = None
    temperature: Optional[float] = None
    max_tokens: Optional[int] = None
    user: Optional[str] = None
    session_id: Optional[str] = None


@router.post("/chat/completions")
async def chat_completions(
    req: ChatCompletionRequest,
    request: Request,
    worker: PairedWorker = Depends(get_token_security().authenticate_request)
):
    """Handle OpenAI-compatible chat completions with streaming and tool support."""
    settings = get_settings()
    cli = get_cli()
    session_manager = get_session_manager()
    metrics = get_metrics()

    model_name = req.model or settings.default_model
    completion_id = f"chatcmpl_{uuid.uuid4().hex[:16]}"
    start_time = time.time()

    # Determine session ID
    session_id = session_manager._derive_session_id(
        explicit_session_id=req.session_id or req.user,
        messages=req.messages,
        client_id=worker.worker_id,
    )

    session = await session_manager.get_or_create_session(session_id)
    session_lock = session_manager.get_lock(session_id)

    # Determine whether this is an incremental turn in an existing conversation or a fresh turn
    async with session_lock:
        use_conversation_id = session.agy_conversation_id
        is_incremental = False
        prompt_to_send = ""

        if use_conversation_id and len(req.messages) > 1:
            # If the last message is a new user prompt or tool result, we can pass just the incremental turn
            last_msg = req.messages[-1]
            if last_msg.get("role") in ("user", "tool"):
                is_incremental = True
                prompt_to_send = PromptBuilder.build_turn_prompt(last_msg)

        if not is_incremental:
            # Fresh conversation or rebuild
            prompt_to_send = PromptBuilder.build_initial_prompt(req.messages, tools=req.tools)
            use_conversation_id = None  # Force new conversation

        logger.info(
            f"Processing completion for {worker.name} (model={model_name}, session={session_id}, "
            f"incremental={is_incremental}, stream={req.stream})"
        )

        # 1. STREAMING RESPONSE
        if req.stream:
            async def event_generator() -> AsyncIterator[str]:
                acc_tokens = 0
                final_usage = {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0}
                new_conv_id = use_conversation_id

                try:
                    # Emit role chunk first
                    first_chunk = {
                        "id": completion_id,
                        "object": "chat.completion.chunk",
                        "created": int(time.time()),
                        "model": model_name,
                        "choices": [
                            {
                                "index": 0,
                                "delta": {"role": "assistant"},
                                "finish_reason": None,
                            }
                        ],
                    }
                    yield f"data: {json.dumps(first_chunk)}\n\n"

                    async for delta, meta in cli.stream_turn(
                        prompt=prompt_to_send,
                        conversation_id=use_conversation_id,
                        model=model_name,
                    ):
                        if meta and meta.get("conversation_id"):
                            new_conv_id = meta["conversation_id"]

                        if delta:
                            acc_tokens += 1
                            yield StreamParser.format_openai_chunk(
                                completion_id=completion_id,
                                model=model_name,
                                delta_text=delta,
                            )

                        if meta and meta.get("usage"):
                            final_usage = meta["usage"]

                    # Emit stop chunk
                    yield StreamParser.format_openai_chunk(
                        completion_id=completion_id,
                        model=model_name,
                        finish_reason="stop",
                        usage=final_usage,
                    )
                    yield StreamParser.format_done_marker()

                    # Update session & metrics
                    duration = time.time() - start_time
                    in_tok = final_usage.get("input_tokens", 0)
                    out_tok = final_usage.get("output_tokens", acc_tokens)
                    await session_manager.update_session(
                        session_id=session_id,
                        agy_conversation_id=new_conv_id,
                        prompt_tokens=in_tok,
                        completion_tokens=out_tok,
                    )
                    metrics.record_request(
                        client_id=worker.name,
                        model=model_name,
                        duration=duration,
                        input_tokens=in_tok,
                        output_tokens=out_tok,
                        is_stream=True,
                        status="SUCCESS",
                    )
                except Exception as e:
                    logger.error(f"Error during streaming turn: {e}")
                    metrics.record_request(
                        client_id=worker.name,
                        model=model_name,
                        duration=time.time() - start_time,
                        input_tokens=0,
                        output_tokens=0,
                        is_stream=True,
                        status="ERROR",
                        error=str(e),
                    )
                    err_chunk = {
                        "error": {
                            "message": str(e),
                            "type": "server_error",
                        }
                    }
                    yield f"data: {json.dumps(err_chunk)}\n\n"
                    yield StreamParser.format_done_marker()

            return StreamingResponse(
                event_generator(),
                media_type="text/event-stream",
                headers={
                    "Cache-Control": "no-cache",
                    "Connection": "keep-alive",
                    "X-Accel-Buffering": "no",
                },
            )

        # 2. NON-STREAMING RESPONSE
        try:
            result = await cli.execute_turn(
                prompt=prompt_to_send,
                conversation_id=use_conversation_id,
                model=model_name,
            )

            response_text = result.get("response", "")
            new_conv_id = result.get("conversation_id") or use_conversation_id
            usage = result.get("usage") or {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0}
            duration = result.get("duration_seconds", time.time() - start_time)

            # Check if model output contains a structured tool call for Agent Zero
            tool_calls, remaining_content = ToolCallAdapter.parse_tool_calls(
                model_text=response_text,
                expected_tools=req.tools
            )

            message_payload: Dict[str, Any] = {"role": "assistant"}
            finish_reason = "stop"

            if tool_calls:
                message_payload["tool_calls"] = tool_calls
                message_payload["content"] = remaining_content if remaining_content else None
                finish_reason = "tool_calls"
                logger.info(f"Emitted {len(tool_calls)} structured tool calls for Worker execution.")
            else:
                message_payload["content"] = response_text

            # Update session and metrics
            in_tok = usage.get("input_tokens", 0)
            out_tok = usage.get("output_tokens", 0)
            await session_manager.update_session(
                session_id=session_id,
                agy_conversation_id=new_conv_id,
                prompt_tokens=in_tok,
                completion_tokens=out_tok,
            )
            metrics.record_request(
                client_id=worker.name,
                model=model_name,
                duration=duration,
                input_tokens=in_tok,
                output_tokens=out_tok,
                is_stream=False,
                status="SUCCESS",
            )

            openai_response = {
                "id": completion_id,
                "object": "chat.completion",
                "created": int(time.time()),
                "model": model_name,
                "choices": [
                    {
                        "index": 0,
                        "message": message_payload,
                        "finish_reason": finish_reason,
                    }
                ],
                "usage": {
                    "prompt_tokens": in_tok,
                    "completion_tokens": out_tok,
                    "total_tokens": in_tok + out_tok,
                },
            }
            return JSONResponse(content=openai_response)

        except AntigravityCLIError as e:
            logger.error(f"Antigravity CLI execution error: {e}")
            metrics.record_request(
                client_id=worker.name,
                model=model_name,
                duration=time.time() - start_time,
                input_tokens=0,
                output_tokens=0,
                is_stream=False,
                status="ERROR",
                error=str(e),
            )
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"Antigravity CLI error: {str(e)}",
            )
        except Exception as e:
            logger.error(f"Unexpected completion error: {e}")
            metrics.record_request(
                client_id=worker.name,
                model=model_name,
                duration=time.time() - start_time,
                input_tokens=0,
                output_tokens=0,
                is_stream=False,
                status="ERROR",
                error=str(e),
            )
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Internal bridge gateway error: {str(e)}",
            )
