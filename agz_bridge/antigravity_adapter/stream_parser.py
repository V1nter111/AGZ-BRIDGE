"""Parses Antigravity stream-json NDJSON events and formats them for OpenAI clients."""
import json
import logging
import time
from typing import Any, AsyncIterator, Dict, Optional, Tuple

logger = logging.getLogger("agz_bridge.antigravity_adapter.stream_parser")


class StreamParser:
    @staticmethod
    def parse_line(line: str) -> Optional[Dict[str, Any]]:
        """Safely parse a single line of NDJSON from agy."""
        clean = line.strip()
        if not clean:
            return None
        try:
            return json.loads(clean)
        except json.JSONDecodeError:
            # Skip non-JSON banner lines or notifications
            return None

    @classmethod
    def format_openai_chunk(
        cls,
        completion_id: str,
        model: str,
        delta_text: Optional[str] = None,
        tool_call_delta: Optional[Dict[str, Any]] = None,
        finish_reason: Optional[str] = None,
        usage: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Format an OpenAI-compatible SSE chunk line."""
        delta: Dict[str, Any] = {}
        if delta_text is not None:
            delta["content"] = delta_text
        if tool_call_delta:
            delta["tool_calls"] = [tool_call_delta]

        chunk: Dict[str, Any] = {
            "id": completion_id,
            "object": "chat.completion.chunk",
            "created": int(time.time()),
            "model": model,
            "choices": [
                {
                    "index": 0,
                    "delta": delta,
                    "finish_reason": finish_reason,
                }
            ],
        }
        if usage:
            chunk["usage"] = {
                "prompt_tokens": usage.get("input_tokens", 0),
                "completion_tokens": usage.get("output_tokens", 0),
                "total_tokens": usage.get("total_tokens", 0),
            }
        return f"data: {json.dumps(chunk)}\n\n"

    @classmethod
    def format_done_marker(cls) -> str:
        return "data: [DONE]\n\n"
