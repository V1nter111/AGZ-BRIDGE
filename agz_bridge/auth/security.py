"""Security dependency and token verification for FastAPI endpoints."""
import logging
from typing import Optional
from fastapi import Header, HTTPException, Request, Security, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from .pairing import PairedWorker, get_pairing_manager

logger = logging.getLogger("agz_bridge.auth.security")
security_scheme = HTTPBearer(auto_error=False)


class TokenSecurity:
    def __init__(self):
        self.pairing_manager = get_pairing_manager()

    async def authenticate_request(
        self,
        request: Request,
        credentials: Optional[HTTPAuthorizationCredentials] = Security(security_scheme),
        api_key_header: Optional[str] = Header(None, alias="x-api-key"),
    ) -> PairedWorker:
        """
        Authenticate worker using Bearer token or x-api-key header.
        Raises HTTP 401 if token is missing, invalid, or revoked.
        """
        raw_token: Optional[str] = None
        if credentials and credentials.credentials:
            raw_token = credentials.credentials.strip()
        elif api_key_header:
            raw_token = api_key_header.strip()

        if not raw_token:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Missing authorization token. Provide 'Authorization: Bearer <token>' header.",
                headers={"WWW-Authenticate": "Bearer"},
            )

        client_ip = request.client.host if request.client else "unknown"
        worker = self.pairing_manager.verify_token(raw_token, client_ip=client_ip)

        if not worker:
            logger.warning(f"Unauthorized request from IP {client_ip}")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid or revoked token.",
                headers={"WWW-Authenticate": "Bearer"},
            )

        return worker


_security_instance: Optional[TokenSecurity] = None


def get_token_security() -> TokenSecurity:
    global _security_instance
    if _security_instance is None:
        _security_instance = TokenSecurity()
    return _security_instance
