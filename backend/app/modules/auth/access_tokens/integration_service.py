"""Operations exposed by the access-token package to auth peers."""

import modules.auth.access_tokens.contracts as access_tokens_contracts
import modules.auth.access_tokens.service as access_tokens_service
import modules.auth.computation as auth_computation

TokenManager = access_tokens_service.TokenManager
TokenType = access_tokens_contracts.TokenType


def get_token_manager() -> access_tokens_service.TokenManager:
    """Return the configured token manager."""
    return access_tokens_service.get_token_manager()


def hmac_sha256(value: str) -> str:
    """Hash a value with the configured JWT secret."""
    secret_key = access_tokens_service.JWT_SECRET_KEY
    if secret_key is None:
        raise ValueError("JWT_SECRET_KEY is not configured")
    return auth_computation.hmac_sha256(value, secret_key)


def scopes_for_access_type(access_type: str) -> tuple[str, ...]:
    """Return the scopes a user of an access type holds."""
    return access_tokens_service.scopes_for_access_type(access_type)
