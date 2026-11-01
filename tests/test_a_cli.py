"""TEST A: Antigravity CLI discovery, auth, execution, and context continuation."""
import pytest
from agz_bridge.antigravity_adapter.cli_runner import AntigravityCLI, get_cli


@pytest.mark.asyncio
async def test_a1_cli_discovery():
    """Verify that Antigravity CLI executable is discovered and valid."""
    cli = get_cli()
    assert cli.agy_path is not None
    assert "agy" in cli.agy_path.lower()


@pytest.mark.asyncio
async def test_a2_cli_auth_and_models():
    """Verify that CLI authentication is active and models can be queried."""
    cli = get_cli()
    models = await cli.list_models()
    assert len(models) > 0
    model_ids = [m["id"] for m in models]
    assert "gemini-3.8-flash-high" in model_ids


@pytest.mark.asyncio
async def test_a3_cli_single_turn_prompt():
    """Verify programmatic prompt execution and token usage reporting."""
    cli = get_cli()
    result = await cli.execute_turn("Say 'AGZ TEST OK'")
    assert result.get("status") == "SUCCESS"
    response = result.get("response", "")
    assert "AGZ TEST OK" in response or "OK" in response
    assert result.get("conversation_id") is not None
    usage = result.get("usage", {})
    assert usage.get("total_tokens", 0) > 0


@pytest.mark.asyncio
async def test_a4_cli_context_continuation():
    """Verify multi-turn conversation maintains context across turns."""
    cli = get_cli()
    # Turn 1
    r1 = await cli.execute_turn("My favorite fruit is Papaya 7788. Remember it.")
    conv_id = r1.get("conversation_id")
    assert conv_id is not None

    # Turn 2 using the same conversation ID
    r2 = await cli.execute_turn(
        "What is my favorite fruit and the number?",
        conversation_id=conv_id
    )
    assert r2.get("status") == "SUCCESS"
    resp2 = r2.get("response", "")
    assert "Papaya" in resp2 or "7788" in resp2
