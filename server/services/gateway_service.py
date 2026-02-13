"""Gateway service for OTLP token validation logic."""
from typing import Optional

from services.database_auth_service import DatabaseAuthService


class GatewayService:
    """Service wrapper for OTLP gateway authentication operations."""

    def __init__(self, auth_service: Optional[DatabaseAuthService] = None):
        self.auth_service = auth_service or DatabaseAuthService()

    def extract_otlp_token(self, header_value: Optional[str]) -> str:
        return (header_value or "").strip()

    def validate_otlp_token(self, token: str) -> Optional[str]:
        return self.auth_service.validate_otlp_token(token)
