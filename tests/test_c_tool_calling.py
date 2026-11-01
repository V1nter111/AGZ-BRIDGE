"""TEST C: Tool call parsing, translation, and worker isolation verification."""
import json
import pytest
from agz_bridge.tool_call_adapter.adapter import ToolCallAdapter


def test_c1_extract_json_tool_format():
    """Verify parsing of standard Agent Zero JSON tool format."""
    text = """Some preamble from model.
```json
{
  "tool_name": "execute_command",
  "tool_args": {
    "command": "python -m unittest",
    "timeout": 30
  }
}
```
Postamble note."""
    tool_calls, remaining = ToolCallAdapter.parse_tool_calls(text)
    assert tool_calls is not None
    assert len(tool_calls) == 1
    call = tool_calls[0]
    assert call["type"] == "function"
    assert call["function"]["name"] == "execute_command"
    args = json.loads(call["function"]["arguments"])
    assert args["command"] == "python -m unittest"
    assert args["timeout"] == 30


def test_c2_extract_agent_zero_full_envelope():
    """Verify parsing of Agent Zero's thoughts + headline + tool envelope."""
    text = json.dumps({
        "thoughts": ["Need to write file", "Then verify"],
        "headline": "Writing target file",
        "tool_name": "write_file",
        "tool_args": {
            "path": "C:\\test\\test.txt",
            "content": "HELLO"
        }
    })
    tool_calls, remaining = ToolCallAdapter.parse_tool_calls(text)
    assert tool_calls is not None
    assert len(tool_calls) == 1
    assert tool_calls[0]["function"]["name"] == "write_file"
    args = json.loads(tool_calls[0]["function"]["arguments"])
    assert args["content"] == "HELLO"


def test_c3_plain_response_no_tools():
    """Verify that normal model answers without tool calls are not misclassified."""
    text = "The Python application has been successfully executed with 100% tests passing."
    tool_calls, remaining = ToolCallAdapter.parse_tool_calls(text)
    assert tool_calls is None
    assert remaining == text
