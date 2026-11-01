"""TEST E: Security, pairing verification, token lifecycle, and secret redaction."""
import time
import pytest
from httpx import ASGITransport, AsyncClient

from agz_bridge.auth.pairing import PairingManager
from agz_bridge.gateway.app import create_app
from agz_bridge.security.validator import sanitize_secrets


def test_e1_pairing_code_single_use(tmp_path):
    """Verify pairing code can only be used once."""
    pm = PairingManager(data_dir=tmp_path)
    code = pm.generate_pairing_code()

    # First attempt -> Success
    ok1, msg1, token1 = pm.validate_and_consume_code(code, "worker1", "Win10", "192.168.1.10")
    assert ok1 is True
    assert token1 is not None

    # Second attempt with same code -> Fails (Already used)
    ok2, msg2, token2 = pm.validate_and_consume_code(code, "worker2", "Win10", "192.168.1.11")
    assert ok2 is False
    assert "already been used" in msg2.lower()
    assert token2 is None


def test_e2_pairing_code_expiration(tmp_path):
    """Verify expired pairing code cannot be consumed."""
    pm = PairingManager(data_dir=tmp_path)
    # Generate code with 1 second lifetime
    code = pm.generate_pairing_code(lifetime_seconds=1)
    time.sleep(1.2)

    ok, msg, token = pm.validate_and_consume_code(code, "worker1", "Win10", "192.168.1.10")
    assert ok is False
    assert "expired" in msg.lower()
    assert token is None


def test_e3_invalid_pairing_code(tmp_path):
    """Verify random invalid pairing code is rejected."""
    pm = PairingManager(data_dir=tmp_path)
    ok, msg, token = pm.validate_and_consume_code("AGZ-INVALID-CODE-9999")
    assert ok is False
    assert "invalid" in msg.lower()


def test_e4_worker_revocation(tmp_path):
    """Verify revoked worker immediately loses token validity."""
    pm = PairingManager(data_dir=tmp_path)
    code = pm.generate_pairing_code()
    _, _, token = pm.validate_and_consume_code(code, "worker1", "Win10")

    worker = pm.verify_token(token)
    assert worker is not None
    assert worker.revoked is False

    # Revoke worker
    pm.revoke_worker(worker.worker_id)

    # Verification must now fail
    worker_after = pm.verify_token(token)
    assert worker_after is None


def test_e5_secret_sanitization():
    """Verify sensitive tokens and pairing codes are redacted from logs."""
    raw_log = "Error connecting with token agz_live_abcdef1234567890abcdef1234567890 and code AGZ-8X7K-9P2M-4W1Q"
    cleaned = sanitize_secrets(raw_log)
    assert "agz_live_" not in cleaned
    assert "AGZ-8X7K-9P2M-4W1Q" not in cleaned
    assert "[REDACTED_SECRET]" in cleaned
