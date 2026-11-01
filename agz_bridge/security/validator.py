"""Network validation middleware and secret sanitization."""
import ipaddress
import logging
import re
from typing import Callable, List
from fastapi import Request, Response, status
from starlette.middleware.base import BaseHTTPMiddleware

from agz_bridge.config.settings import get_settings

logger = logging.getLogger("agz_bridge.security.validator")

# Regex patterns to scrub sensitive material from logs/exceptions
SECRET_PATTERNS = [
    re.compile(r"agz_live_[a-zA-Z0-9_-]{16,}", re.IGNORECASE),
    re.compile(r"AGZ-[A-Z0-9]{4}-[A-Z0-9]{4}-[A-Z0-9]{4}", re.IGNORECASE),
    re.compile(r"Bearer\s+[a-zA-Z0-9_\-\.]{10,}", re.IGNORECASE),
    re.compile(r"ya29\.[a-zA-Z0-9_\-]{20,}", re.IGNORECASE),  # Google OAuth access tokens
]


def sanitize_secrets(text: str) -> str:
    """Mask secrets and tokens in log strings."""
    if not isinstance(text, str):
        return text
    sanitized = text
    for pattern in SECRET_PATTERNS:
        sanitized = pattern.sub("[REDACTED_SECRET]", sanitized)
    return sanitized


class NetworkSecurityMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, allowed_cidrs: List[str] | None = None):
        super().__init__(app)
        settings = get_settings()
        cidrs = allowed_cidrs or settings.allowed_cidrs
        self.networks = [ipaddress.ip_network(cidr.strip(), strict=False) for cidr in cidrs]

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        client_host = request.client.host if request.client else None

        # Allow swagger/openapi/health on localhost or internal network
        if client_host:
            try:
                ip = ipaddress.ip_address(client_host)
                # Check if IP is in allowed private networks
                is_allowed = any(ip in net for net in self.networks)
                if not is_allowed:
                    logger.warning(f"Blocked connection from unauthorized IP: {client_host}")
                    return Response(
                        content="Forbidden: Connection must originate from a private network or Tailscale.",
                        status_code=status.HTTP_403_FORBIDDEN
                    )
            except ValueError:
                # Invalid IP representation
                logger.warning(f"Invalid client IP: {client_host}")
                return Response(content="Forbidden", status_code=status.HTTP_403_FORBIDDEN)

        response = await call_next(request)
        return response
