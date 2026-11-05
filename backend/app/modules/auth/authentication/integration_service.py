"""Principal and sign-in lockout operations exposed to the authentication peers."""

from fastapi import Request
from sqlalchemy.orm import Session

import core.dependencies as core_dependencies
import core.logger as core_logger
import core.network as core_network
import modules.auth.access_tokens.integration_service as access_tokens_integration
import modules.auth.authentication.failed_login_store as failed_login_store
import modules.auth.authentication.principal_service as principal_service
import modules.auth.contracts as auth_contracts
import modules.auth.lockout.contracts as lockout_contracts

logger = core_logger.get_logger(__name__)


def resolve_from_access_token(access_token: str, db: Session) -> auth_contracts.Principal:
    """Resolve and validate an access token against the current database state."""
    return principal_service.resolve_from_access_token(access_token, access_tokens_integration.get_token_manager(), db)


def resolve_from_api_key(raw_key: str, request: Request, db: Session) -> auth_contracts.Principal:
    """Resolve and validate an API key against the current database state."""
    return principal_service.resolve_from_api_key(raw_key, request.url.path, core_network.get_ip_address(request), db)


def clear_account_login_lockout(username: str) -> None:
    """Lift the account-wide sign-in lock and failure count of a username after its password was replaced.

    A credential change that follows an outage of the shared state still succeeds; the lock then ends on its own or at
    the next successful sign-in.

    Args:
        username: The username whose account-wide failed sign-ins are forgotten.
    """
    try:
        failed_login_store.FailedLoginAttempts(core_dependencies.get_platform_state()).reset_account(username)
    except lockout_contracts.AuthSecurityStoreUnavailableError:
        logger.warning("Account sign-in lock was not cleared because the shared state is unavailable")
