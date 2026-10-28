"""Principal operations exposed to the authentication dependency boundary."""

from datetime import datetime

from fastapi import Request
from sqlalchemy.orm import Session

import modules.auth.access_tokens.integration_service as access_tokens_integration
import modules.auth.authentication.principal_service as principal_service
import modules.auth.authentication.service as authentication_service
import modules.auth.contracts as auth_contracts
import modules.server_settings.contracts as server_settings_contracts
import modules.users.users.schema as users_schema


def resolve_from_access_token(access_token: str, db: Session) -> auth_contracts.Principal:
    """Resolve and validate an access token against the current database state."""
    return principal_service.resolve_from_access_token(access_token, access_tokens_integration.get_token_manager(), db)


def resolve_from_api_key(raw_key: str, request: Request, db: Session) -> auth_contracts.Principal:
    """Resolve and validate an API key against the current database state."""
    return principal_service.resolve_from_api_key(raw_key, request, db)


def create_tokens(
    user: users_schema.UsersRead,
    token_manager: access_tokens_integration.TokenManager,
    policy: server_settings_contracts.SessionPolicy,
    session_id: str | None = None,
) -> tuple[str, datetime, str, datetime, str, str]:
    """Create a token pair for an identity-provider session exchange."""
    return authentication_service.create_tokens(user, token_manager, policy, session_id)
