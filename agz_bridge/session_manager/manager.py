"""Manages multi-turn conversation isolation, session locking, and lifetime."""
import asyncio
import hashlib
import json
import logging
import time
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

logger = logging.getLogger("agz_bridge.session_manager")


class SessionInfo(BaseModel):
    session_id: str
    agy_conversation_id: Optional[str] = None
    created_at: float
    last_activity: float
    turn_count: int = 0
    total_prompt_tokens: int = 0
    total_completion_tokens: int = 0
    metadata: Dict[str, Any] = Field(default_factory=dict)


class SessionManager:
    def __init__(self, session_ttl_seconds: int = 86400):
        self.session_ttl = session_ttl_seconds
        self._sessions: Dict[str, SessionInfo] = {}
        self._locks: Dict[str, asyncio.Lock] = {}
        self._global_lock = asyncio.Lock()

    def _derive_session_id(
        self,
        explicit_session_id: Optional[str] = None,
        messages: Optional[List[Dict[str, Any]]] = None,
        client_id: Optional[str] = None
    ) -> str:
        """
        Derive or validate a unique session identifier.
        If client provides a session id, use it.
        Otherwise derive from initial user prompt + client ID.
        """
        if explicit_session_id and explicit_session_id.strip():
            return explicit_session_id.strip()

        if messages and len(messages) > 0:
            first_user_content = ""
            for m in messages:
                if m.get("role") == "user":
                    c = m.get("content", "")
                    first_user_content = str(c)[:100]
                    break
            if first_user_content:
                prefix = f"{client_id or 'anon'}:{first_user_content}"
                digest = hashlib.sha256(prefix.encode("utf-8")).hexdigest()[:16]
                return f"sess_{digest}"

        return f"sess_{hashlib.sha256(str(time.time()).encode()).hexdigest()[:16]}"

    async def get_or_create_session(
        self,
        session_id: str,
        initial_agy_conv_id: Optional[str] = None,
    ) -> SessionInfo:
        async with self._global_lock:
            now = time.time()
            if session_id in self._sessions:
                sess = self._sessions[session_id]
                sess.last_activity = now
                if initial_agy_conv_id and not sess.agy_conversation_id:
                    sess.agy_conversation_id = initial_agy_conv_id
                return sess

            # Create new session
            sess = SessionInfo(
                session_id=session_id,
                agy_conversation_id=initial_agy_conv_id,
                created_at=now,
                last_activity=now,
                turn_count=0
            )
            self._sessions[session_id] = sess
            self._locks[session_id] = asyncio.Lock()
            return sess

    def get_lock(self, session_id: str) -> asyncio.Lock:
        """Get the per-session lock to serialize multi-turn requests."""
        if session_id not in self._locks:
            self._locks[session_id] = asyncio.Lock()
        return self._locks[session_id]

    async def update_session(
        self,
        session_id: str,
        agy_conversation_id: Optional[str] = None,
        prompt_tokens: int = 0,
        completion_tokens: int = 0,
    ):
        async with self._global_lock:
            if session_id in self._sessions:
                sess = self._sessions[session_id]
                sess.last_activity = time.time()
                sess.turn_count += 1
                sess.total_prompt_tokens += prompt_tokens
                sess.total_completion_tokens += completion_tokens
                if agy_conversation_id:
                    sess.agy_conversation_id = agy_conversation_id

    async def list_active_sessions(self) -> List[SessionInfo]:
        """List currently tracked sessions."""
        now = time.time()
        # Clean up stale sessions
        stale = [
            sid for sid, s in self._sessions.items()
            if now - s.last_activity > self.session_ttl
        ]
        for sid in stale:
            self._sessions.pop(sid, None)
            self._locks.pop(sid, None)

        return list(self._sessions.values())


_session_manager_instance: Optional[SessionManager] = None


def get_session_manager() -> SessionManager:
    global _session_manager_instance
    if _session_manager_instance is None:
        _session_manager_instance = SessionManager()
    return _session_manager_instance
