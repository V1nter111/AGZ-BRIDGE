"""Extracts structured tool calls from model output and translates to OpenAI tool_calls structure."""
import json
import logging
import re
import uuid
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger("agz_bridge.tool_call_adapter")


class ToolCallAdapter:
    @staticmethod
    def extract_json_objects(text: str) -> List[Dict[str, Any]]:
        """Extract valid JSON objects from raw response text, including code fences."""
        results: List[Dict[str, Any]] = []
        if not text:
            return results

        trimmed = text.strip()

        # 1. Direct JSON parse
        if trimmed.startswith("{") and trimmed.endswith("}"):
            try:
                obj = json.loads(trimmed)
                if isinstance(obj, dict):
                    results.append(obj)
                    return results
            except json.JSONDecodeError:
                pass

        # 2. Extract from markdown code fences: ```json ... ``` or ``` ... ```
        fence_pattern = re.compile(r"```(?:json)?\s*(\{[\s\S]*?\})\s*```", re.IGNORECASE)
        for match in fence_pattern.finditer(text):
            try:
                obj = json.loads(match.group(1))
                if isinstance(obj, dict):
                    results.append(obj)
            except json.JSONDecodeError:
                pass

        if results:
            return results

        # 3. Find any balanced curly brace JSON objects in text
        start_idx = 0
        while True:
            start = text.find("{", start_idx)
            if start == -1:
                break
            depth = 0
            in_string = False
            escape = False
            end = -1
            for i in range(start, len(text)):
                ch = text[i]
                if ch == '"' and not escape:
                    in_string = not in_string
                elif not in_string:
                    if ch == '{':
                        depth += 1
                    elif ch == '}':
                        depth -= 1
                        if depth == 0:
                            end = i + 1
                            break
                if ch == '\\' and not escape:
                    escape = True
                else:
                    escape = False

            if end != -1:
                candidate = text[start:end]
                try:
                    obj = json.loads(candidate)
                    if isinstance(obj, dict):
                        results.append(obj)
                except json.JSONDecodeError:
                    pass
                start_idx = end
            else:
                break

        return results

    @classmethod
    def parse_tool_calls(
        cls,
        model_text: str,
        expected_tools: Optional[List[Dict[str, Any]]] = None
    ) -> Tuple[Optional[List[Dict[str, Any]]], str]:
        """
        Check if model output represents a tool call.
        Returns:
            (tool_calls: Optional[List[Dict[str, Any]]], remaining_text: str)
            If tool_calls is not None, finish_reason should be 'tool_calls'.
        """
        known_tool_names = set()
        if expected_tools:
            for t in expected_tools:
                if t.get("type") == "function" and "function" in t:
                    known_tool_names.add(t["function"].get("name"))

        extracted = cls.extract_json_objects(model_text)
        tool_calls: List[Dict[str, Any]] = []

        for obj in extracted:
            # Format A: {"tool_name": "...", "tool_args": {...}}
            if "tool_name" in obj and ("tool_args" in obj or "arguments" in obj):
                name = str(obj.get("tool_name")).strip()
                args = obj.get("tool_args") if "tool_args" in obj else obj.get("arguments", {})
                args_str = json.dumps(args) if isinstance(args, dict) else str(args)
                tool_calls.append({
                    "id": f"call_{uuid.uuid4().hex[:12]}",
                    "type": "function",
                    "function": {
                        "name": name,
                        "arguments": args_str,
                    }
                })
            # Format B: {"function": {"name": "...", "arguments": ...}}
            elif "function" in obj and isinstance(obj["function"], dict) and "name" in obj["function"]:
                fn = obj["function"]
                name = str(fn.get("name")).strip()
                args = fn.get("arguments", {})
                args_str = json.dumps(args) if isinstance(args, dict) else str(args)
                tool_calls.append({
                    "id": f"call_{uuid.uuid4().hex[:12]}",
                    "type": "function",
                    "function": {
                        "name": name,
                        "arguments": args_str,
                    }
                })
            # Format C: {"name": "<known_tool>", "arguments": ...}
            elif "name" in obj and obj["name"] in known_tool_names:
                name = str(obj["name"]).strip()
                args = obj.get("arguments") or obj.get("parameters") or {}
                args_str = json.dumps(args) if isinstance(args, dict) else str(args)
                tool_calls.append({
                    "id": f"call_{uuid.uuid4().hex[:12]}",
                    "type": "function",
                    "function": {
                        "name": name,
                        "arguments": args_str,
                    }
                })

        if tool_calls:
            return tool_calls, ""

        return None, model_text
