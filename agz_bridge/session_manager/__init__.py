"""Session management and conversation isolation."""
from .manager import SessionManager, get_session_manager

__all__ = ["SessionManager", "get_session_manager"]
