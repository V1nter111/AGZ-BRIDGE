"""TEST B: API Gateway endpoints, streaming, and concurrency."""
import json
import pytest
from httpx import ASGITransport, AsyncClient

from agz_bridge.auth.pairing import get_pairing_manager
from agz_bridge.gateway.app import create_app


@pytest.fixture
def test_setup():
    app = create_app()
    manager = get_pairing_manager()
    code = manager.generate_pairing_code()
    success, msg, token = manager.validate_and_consume_code(
        code=code,
        worker_name="test-worker",
        os_info="Windows 11",
        client_ip="127.0.0.1"
    )
    return app, token


@pytest.mark.asyncio
async def test_b1_health_and_public_endpoints(test_setup):
    app, _ = test_setup
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        r = await ac.get("/health")
        assert r.status_code == 200
        assert r.json()["status"] == "healthy"

        r_pair = await ac.get("/api/pair/status")
        assert r_pair.status_code == 200
        assert r_pair.json()["service"] == "AGZ Bridge Host"


@pytest.mark.asyncio
async def test_b2_models_endpoint(test_setup):
    app, token = test_setup
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        # 1. Without auth -> 401
        r_unauth = await ac.get("/v1/models")
        assert r_unauth.status_code == 401

        # 2. With auth -> 200 list
        r_auth = await ac.get("/v1/models", headers={"Authorization": f"Bearer {token}"})
        assert r_auth.status_code == 200
        data = r_auth.json()
        assert data["object"] == "list"
        ids = [m["id"] for m in data["data"]]
        assert "gemini-3.8-flash-high" in ids


@pytest.mark.asyncio
async def test_b3_chat_completions_json(test_setup):
    app, token = test_setup
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        payload = {
            "model": "gemini-3.8-flash-high",
            "messages": [
                {"role": "user", "content": "Respond strictly with the single word 'PASS'."}
            ],
            "stream": False
        }
        r = await ac.post(
            "/v1/chat/completions",
            json=payload,
            headers={"Authorization": f"Bearer {token}"},
            timeout=30.0
        )
        assert r.status_code == 200
        data = r.json()
        assert data["object"] == "chat.completion"
        assert len(data["choices"]) > 0
        content = data["choices"][0]["message"]["content"]
        assert "PASS" in content
        assert data["usage"]["total_tokens"] > 0


@pytest.mark.asyncio
async def test_b4_chat_completions_streaming(test_setup):
    app, token = test_setup
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        payload = {
            "model": "gemini-3.8-flash-high",
            "messages": [
                {"role": "user", "content": "Count from 1 to 3."}
            ],
            "stream": True
        }
        r = await ac.post(
            "/v1/chat/completions",
            json=payload,
            headers={"Authorization": f"Bearer {token}"},
            timeout=30.0
        )
        assert r.status_code == 200
        assert "text/event-stream" in r.headers["content-type"]
        text = r.text
        assert "data: " in text
        assert "[DONE]" in text
