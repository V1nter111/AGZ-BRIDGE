"""One-time pairing code generator and paired worker device registry."""
import hashlib
import json
import logging
import secrets
import string
import time
from pathlib import Path
from typing import Dict, List, Optional
from pydantic import BaseModel, Field

from agz_bridge.config.settings import get_settings

logger = logging.getLogger("agz_bridge.auth.pairing")


class PairingCode(BaseModel):
    code: str
    created_at: float
    expires_at: float
    used: bool = False
    used_at: Optional[float] = None
    used_by_worker: Optional[str] = None


class PairedWorker(BaseModel):
    worker_id: str
    name: str
    os_info: str
    paired_at: float
    last_seen: float
    token_hash: str
    client_ip: str
    revoked: bool = False


class PairingManager:
    def __init__(self, data_dir: Optional[Path] = None):
        self.settings = get_settings()
        self.data_dir = data_dir or (self.settings.data_dir / "data")
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.codes_file = self.data_dir / "pairing_codes.json"
        self.workers_file = self.data_dir / "paired_workers.json"
        self._codes: Dict[str, PairingCode] = {}
        self._workers: Dict[str, PairedWorker] = {}
        self._load()

    def _load(self):
        """Load stored pairing codes and workers from disk."""
        if self.codes_file.exists():
            try:
                data = json.loads(self.codes_file.read_text(encoding="utf-8"))
                for k, v in data.items():
                    self._codes[k] = PairingCode(**v)
            except Exception as e:
                logger.error(f"Failed to load pairing codes: {e}")

        if self.workers_file.exists():
            try:
                data = json.loads(self.workers_file.read_text(encoding="utf-8"))
                for k, v in data.items():
                    self._workers[k] = PairedWorker(**v)
            except Exception as e:
                logger.error(f"Failed to load paired workers: {e}")

    def _save(self):
        """Persist pairing state to disk atomically."""
        try:
            temp_codes = self.codes_file.with_suffix(".tmp")
            temp_codes.write_text(
                json.dumps({k: v.model_dump() for k, v in self._codes.items()}, indent=2),
                encoding="utf-8"
            )
            temp_codes.replace(self.codes_file)

            temp_workers = self.workers_file.with_suffix(".tmp")
            temp_workers.write_text(
                json.dumps({k: v.model_dump() for k, v in self._workers.items()}, indent=2),
                encoding="utf-8"
            )
            temp_workers.replace(self.workers_file)
        except Exception as e:
            logger.error(f"Failed to persist pairing state: {e}")

    def generate_pairing_code(self, lifetime_seconds: Optional[int] = None) -> str:
        """Generate a cryptographically secure, readable one-time pairing code."""
        lifetime = lifetime_seconds or self.settings.pairing_code_lifetime_seconds
        # Format: AGZ-XXXX-YYYY-ZZZZ using uppercase alphanumeric characters without ambiguous chars (no 0/O, 1/I)
        alphabet = "23456789ABCDEFGHJKLMNPQRSTUVWXYZ"
        part1 = "".join(secrets.choice(alphabet) for _ in range(4))
        part2 = "".join(secrets.choice(alphabet) for _ in range(4))
        part3 = "".join(secrets.choice(alphabet) for _ in range(4))
        code = f"AGZ-{part1}-{part2}-{part3}"

        now = time.time()
        record = PairingCode(
            code=code,
            created_at=now,
            expires_at=now + lifetime,
            used=False
        )
        self._codes[code] = record
        self._save()
        logger.info(f"Generated new pairing code: {code} (valid for {lifetime}s)")
        return code

    def get_active_pairing_code(self) -> Optional[str]:
        """Return the most recently generated active, non-expired, unused code, or None."""
        now = time.time()
        valid = [c for c in self._codes.values() if not c.used and c.expires_at > now]
        if valid:
            valid.sort(key=lambda x: x.created_at, reverse=True)
            return valid[0].code
        return None

    def validate_and_consume_code(
        self,
        code: str,
        worker_name: str = "worker",
        os_info: str = "Windows",
        client_ip: str = "127.0.0.1"
    ) -> tuple[bool, str, Optional[str]]:
        """
        Validate pairing code and issue a long-term API token.
        Returns: (success: bool, message: str, token: Optional[str])
        """
        normalized_code = code.strip().upper()
        if normalized_code not in self._codes:
            return False, "Invalid pairing code.", None

        record = self._codes[normalized_code]
        now = time.time()

        if record.used:
            return False, "Pairing code has already been used.", None

        if record.expires_at < now:
            return False, "Pairing code has expired.", None

        # Atomically consume the code
        record.used = True
        record.used_at = now
        record.used_by_worker = worker_name

        # Generate unique API token for this worker
        raw_token = f"agz_live_{secrets.token_hex(24)}"
        token_hash = hashlib.sha256(raw_token.encode("utf-8")).hexdigest()
        worker_id = f"worker_{secrets.token_hex(6)}"

        worker = PairedWorker(
            worker_id=worker_id,
            name=worker_name,
            os_info=os_info,
            paired_at=now,
            last_seen=now,
            token_hash=token_hash,
            client_ip=client_ip,
            revoked=False
        )
        self._workers[worker_id] = worker
        self._save()

        logger.info(f"Worker paired successfully: {worker_name} ({worker_id}) from {client_ip}")
        return True, "Paired successfully.", raw_token

    def verify_token(self, token: str, client_ip: str = "") -> Optional[PairedWorker]:
        """Verify worker token and update last seen timestamp."""
        if not token or not token.startswith("agz_live_"):
            return None

        token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
        for worker in self._workers.values():
            if worker.token_hash == token_hash:
                if worker.revoked:
                    logger.warning(f"Rejected revoked worker token for: {worker.name} ({worker.worker_id})")
                    return None
                # Update last seen
                worker.last_seen = time.time()
                if client_ip:
                    worker.client_ip = client_ip
                self._save()
                return worker
        return None

    def revoke_worker(self, worker_id: str) -> bool:
        """Revoke a paired worker by its ID."""
        if worker_id in self._workers:
            self._workers[worker_id].revoked = True
            self._save()
            logger.info(f"Revoked worker: {worker_id}")
            return True
        return False

    def list_workers(self) -> List[PairedWorker]:
        """Return list of all paired workers."""
        return list(self._workers.values())


_pairing_manager_instance: Optional[PairingManager] = None


def get_pairing_manager() -> PairingManager:
    global _pairing_manager_instance
    if _pairing_manager_instance is None:
        _pairing_manager_instance = PairingManager()
    return _pairing_manager_instance
