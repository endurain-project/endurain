"""Request-parameter types for the account-security routes."""

from datetime import UTC, datetime
from typing import Annotated

from fastapi import Body, Depends
from fastapi.exceptions import RequestValidationError

import core.dependencies as core_dependencies
import modules.auth.api_keys.schema as api_keys_schema
import modules.server_settings.integration_service as server_settings_integration


def api_key_expiry(
    data: Annotated[api_keys_schema.UserApiKeyCreate, Body()],
    db: core_dependencies.DbSession,
) -> datetime:
    """Resolve the expiry of a new API key against the server's maximum API key lifetime.

    Args:
        data: The create request.
        db: Database session dependency.

    Returns:
        The requested expiry, or the latest one the server allows when none was requested.

    Raises:
        RequestValidationError: When the requested expiry is later than the maximum lifetime allows (422).
    """
    latest = datetime.now(UTC) + server_settings_integration.get_session_policy(db).api_key_max_lifetime
    if data.expires_at is None:
        return latest
    if data.expires_at > latest:
        raise RequestValidationError(
            [
                {
                    "type": "value_error",
                    "loc": ("body", "expires_at"),
                    "msg": f"expires_at must be no later than {latest.isoformat()}",
                    "input": data.expires_at.isoformat(),
                }
            ]
        )
    return data.expires_at


#: The expiry of the API key being created, declared as ``expires_at: account_security_dependencies.ApiKeyExpiry``.
ApiKeyExpiry = Annotated[datetime, Depends(api_key_expiry)]
