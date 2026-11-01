"""Subprocess runner and lifecycle manager for Antigravity CLI."""
import asyncio
import json
import logging
import os
import shutil
import time
from pathlib import Path
from typing import Any, AsyncIterator, Dict, List, Optional, Tuple

from agz_bridge.config.settings import get_settings
from .stream_parser import StreamParser

logger = logging.getLogger("agz_bridge.antigravity_adapter.cli_runner")


class AntigravityCLIError(Exception):
    """Exception raised when Antigravity CLI fails."""
    pass


class AntigravityCLI:
    def __init__(self, agy_path: Optional[str] = None):
        self.settings = get_settings()
        self.agy_path = agy_path or self.settings.agy_path
        self._validate_binary()

    def _validate_binary(self):
        """Ensure agy executable exists and is runnable."""
        if not self.agy_path or not (Path(self.agy_path).exists() or shutil.which(self.agy_path)):
            # Check default path
            default_path = Path.home() / "AppData" / "Local" / "agy" / "bin" / "agy.exe"
            if default_path.exists():
                self.agy_path = str(default_path)
            else:
                raise AntigravityCLIError(
                    f"Antigravity CLI executable not found at '{self.agy_path}'. "
                    "Please ensure Antigravity CLI is installed."
                )

    async def list_models(self) -> List[Dict[str, str]]:
        """Query available models from agy."""
        cmd = [self.agy_path, "models"]
        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=15)
            lines = stdout.decode("utf-8", errors="replace").splitlines()
            models = []
            for line in lines:
                parts = line.strip().split("\t")
                if len(parts) >= 2:
                    model_id, display_name = parts[0].strip(), parts[1].strip()
                    if model_id and not model_id.startswith("Fetching"):
                        models.append({"id": model_id, "name": display_name})
                elif len(parts) == 1 and parts[0] and not parts[0].startswith("Fetching"):
                    models.append({"id": parts[0].strip(), "name": parts[0].strip()})

            if not models:
                # Return standard models if parsing had no results
                return [{"id": m, "name": m} for m in self.settings.available_models]
            return models
        except Exception as e:
            logger.warning(f"Failed to fetch models from agy: {e}. Using fallback defaults.")
            return [{"id": m, "name": m} for m in self.settings.available_models]

    async def execute_turn(
        self,
        prompt: str,
        conversation_id: Optional[str] = None,
        model: Optional[str] = None,
        timeout_seconds: Optional[int] = None,
    ) -> Dict[str, Any]:
        """
        Execute a non-streaming turn using Antigravity CLI.
        Returns parsed JSON dict with 'response', 'conversation_id', 'usage', etc.
        """
        timeout = timeout_seconds or self.settings.cli_timeout_seconds
        cmd = [self.agy_path, "--output-format", "json"]

        if model:
            cmd.extend(["--model", model])
        if conversation_id:
            cmd.extend(["--conversation", conversation_id])

        cmd.extend(["-p", prompt])

        start_time = time.time()
        logger.debug(f"Executing agy turn (conv={conversation_id}, model={model}, prompt_len={len(prompt)})")

        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        try:
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
        except asyncio.TimeoutError:
            try:
                proc.kill()
            except Exception:
                pass
            raise AntigravityCLIError(f"Antigravity CLI timed out after {timeout} seconds.")

        duration = time.time() - start_time
        stdout_str = stdout.decode("utf-8", errors="replace")
        stderr_str = stderr.decode("utf-8", errors="replace")

        if proc.returncode != 0 and not stdout_str.strip():
            logger.error(f"agy exited with code {proc.returncode}: {stderr_str}")
            raise AntigravityCLIError(f"Antigravity CLI failed (code {proc.returncode}): {stderr_str}")

        # Parse JSON output
        try:
            # Find the JSON object in stdout (it might have warnings on lines before)
            json_start = stdout_str.find("{")
            if json_start != -1:
                result = json.loads(stdout_str[json_start:])
                result["duration_seconds"] = duration
                return result
            else:
                return {
                    "conversation_id": conversation_id or "",
                    "status": "SUCCESS",
                    "response": stdout_str,
                    "usage": {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0},
                    "duration_seconds": duration,
                }
        except json.JSONDecodeError as e:
            logger.warning(f"Failed to decode agy JSON response: {e}. Raw stdout: {stdout_str}")
            return {
                "conversation_id": conversation_id or "",
                "status": "SUCCESS",
                "response": stdout_str,
                "usage": {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0},
                "duration_seconds": duration,
            }

    async def stream_turn(
        self,
        prompt: str,
        conversation_id: Optional[str] = None,
        model: Optional[str] = None,
        timeout_seconds: Optional[int] = None,
    ) -> AsyncIterator[Tuple[str, Optional[Dict[str, Any]]]]:
        """
        Stream tokens from agy using --output-format stream-json.
        Yields tuples: (delta_text: str, metadata: Optional[Dict[str, Any]])
        When finished, metadata contains final usage and conversation_id.
        """
        timeout = timeout_seconds or self.settings.cli_timeout_seconds
        cmd = [self.agy_path, "--output-format", "stream-json"]

        if model:
            cmd.extend(["--model", model])
        if conversation_id:
            cmd.extend(["--conversation", conversation_id])

        cmd.extend(["-p", prompt])

        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        active_conv_id = conversation_id
        final_usage = None
        full_response_acc = []

        try:
            while True:
                line_bytes = await asyncio.wait_for(proc.stdout.readline(), timeout=timeout)
                if not line_bytes:
                    break
                line = line_bytes.decode("utf-8", errors="replace")
                data = StreamParser.parse_line(line)
                if not data:
                    continue

                event = data.get("event")
                if event == "init":
                    active_conv_id = data.get("conversation_id")
                elif event == "step_update":
                    step = data.get("step_update", {})
                    delta = step.get("text_delta")
                    if delta:
                        full_response_acc.append(delta)
                        yield delta, {"conversation_id": active_conv_id}
                    if step.get("usage"):
                        final_usage = step.get("usage")
                elif event == "result":
                    res = data.get("result", {})
                    active_conv_id = res.get("conversation_id") or active_conv_id
                    if res.get("usage"):
                        final_usage = res.get("usage")

            await proc.wait()
        except asyncio.TimeoutError:
            try:
                proc.kill()
            except Exception:
                pass
            raise AntigravityCLIError(f"Streaming turn timed out after {timeout} seconds.")
        except Exception:
            try:
                proc.kill()
            except Exception:
                pass
            raise

        # Final metadata yield
        yield "", {
            "conversation_id": active_conv_id,
            "usage": final_usage or {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0},
            "full_response": "".join(full_response_acc),
            "status": "DONE"
        }


_cli_instance: Optional[AntigravityCLI] = None


def get_cli() -> AntigravityCLI:
    global _cli_instance
    if _cli_instance is None:
        _cli_instance = AntigravityCLI()
    return _cli_instance
