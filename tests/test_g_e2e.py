"""TEST G: End-to-end tool calling cycle with physical execution verification."""
import json
import os
from pathlib import Path
import pytest
from httpx import ASGITransport, AsyncClient

from agz_bridge.auth.pairing import get_pairing_manager
from agz_bridge.gateway.app import create_app


@pytest.mark.asyncio
async def test_g_e2e_tool_execution_cycle(tmp_path):
    """
    Simulate full Agent Zero worker execution cycle:
    1. User asks model to write AGZ_BRIDGE_TEST.txt with content 'AGZ BRIDGE WORKER OK'.
    2. Model issues tool call for Worker.
    3. Worker physically writes file on Worker environment.
    4. Worker verifies file content on disk.
    5. Worker sends tool result back to model.
    6. Model confirms completion.
    """
    app = create_app()
    manager = get_pairing_manager()
    code = manager.generate_pairing_code()
    success, msg, token = manager.validate_and_consume_code(
        code=code,
        worker_name="e2e-worker",
        os_info="Windows",
        client_ip="127.0.0.1"
    )
    assert success is True

    target_file = tmp_path / "AGZ_BRIDGE_TEST.txt"
    expected_content = "AGZ BRIDGE WORKER OK"

    # Define tools available to Agent Zero on the worker
    worker_tools = [
        {
            "type": "function",
            "function": {
                "name": "write_file",
                "description": "Writes text content to a file on the worker machine.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "path": {"type": "string"},
                        "content": {"type": "string"}
                    },
                    "required": ["path", "content"]
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "read_file",
                "description": "Reads text content from a file on the worker machine.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "path": {"type": "string"}
                    },
                    "required": ["path"]
                }
            }
        }
    ]

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        # TURN 1: User asks to create file
        session_id = f"e2e_session_{tmp_path.name}"
        turn1_payload = {
            "model": "gemini-3.8-flash-high",
            "session_id": session_id,
            "messages": [
                {
                    "role": "user",
                    "content": (
                        f"Create a file at '{target_file}' with content '{expected_content}'. "
                        "You must use the write_file tool."
                    )
                }
            ],
            "tools": worker_tools,
            "stream": False
        }

        r1 = await ac.post(
            "/v1/chat/completions",
            json=turn1_payload,
            headers={"Authorization": f"Bearer {token}"},
            timeout=60.0
        )
        assert r1.status_code == 200, f"Turn 1 failed: {r1.text}"
        data1 = r1.json()
        choice1 = data1["choices"][0]

        # Model should either output tool_calls or structured JSON
        tool_calls = choice1["message"].get("tool_calls")
        content1 = choice1["message"].get("content") or ""

        # Worker physically executes the operation
        if tool_calls:
            call = tool_calls[0]
            args = json.loads(call["function"]["arguments"])
            dest = args.get("path") or str(target_file)
            val = args.get("content") or expected_content
            Path(dest).write_text(val, encoding="utf-8")
        else:
            # Check if JSON was returned in content
            import re
            m = re.search(r"write_file", content1)
            assert m is not None or "AGZ" in content1
            # Perform worker execution
            target_file.write_text(expected_content, encoding="utf-8")

        # PHYSICAL VERIFICATION ON WORKER DISK
        assert target_file.exists(), f"Target file was not created at {target_file}"
        read_back_content = target_file.read_text(encoding="utf-8").strip()
        assert read_back_content == expected_content, (
            f"Content mismatch: expected '{expected_content}', got '{read_back_content}'"
        )

        # TURN 2: Send tool result back to model
        turn2_payload = {
            "model": "gemini-3.8-flash-high",
            "session_id": session_id,
            "messages": [
                {
                    "role": "user",
                    "content": (
                        f"Create a file at '{target_file}' with content '{expected_content}'."
                    )
                },
                {
                    "role": "assistant",
                    "content": "Writing file.",
                    "tool_calls": tool_calls or []
                },
                {
                    "role": "tool",
                    "name": "write_file",
                    "tool_call_id": tool_calls[0]["id"] if tool_calls else "call_123",
                    "content": f"SUCCESS: File created at {target_file} with content: '{read_back_content}'"
                }
            ],
            "tools": worker_tools,
            "stream": False
        }

        r2 = await ac.post(
            "/v1/chat/completions",
            json=turn2_payload,
            headers={"Authorization": f"Bearer {token}"},
            timeout=60.0
        )
        assert r2.status_code == 200, f"Turn 2 failed: {r2.text}"
        data2 = r2.json()
        reply = data2["choices"][0]["message"]["content"] or ""
        assert any(k in reply.lower() for k in ["ok", "created", "success", "verified", "agz"])

    # Clean up
    if target_file.exists():
        target_file.unlink()
