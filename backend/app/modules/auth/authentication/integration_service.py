"""Principal operations exposed to the authentication dependency boundary."""

from fastapi import Request
from sqlalchemy.orm import Session

import core.network as core_network
import modules.auth.access_tokens.integration_service as access_tokens_integration
import modules.auth.authentication.principal_service as principal_service
import modules.auth.contracts as auth_contracts


def resolve_from_access_token(access_token: str, db: Session) -> auth_contracts.Principal:
    """Resolve and validate an access token against the current database state."""
    return principal_service.resolve_from_access_token(access_token, access_tokens_integration.get_token_manager(), db)


def resolve_from_api_key(raw_key: str, request: Request, db: Session) -> auth_contracts.Principal:
    """Resolve and validate an API key against the current database state."""
    return principal_service.resolve_from_api_key(raw_key, request.url.path, core_network.get_ip_address(request), db)
