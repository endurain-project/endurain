"""Principal and sign-in lockout operations exposed to the authentication peers."""

from fastapi import Request
from sqlalchemy.orm import Session

import core.dependencies as core_dependencies
import core.logger as core_logger
import core.network as core_network
import modules.auth.access_tokens.integration_service as access_tokens_integration
import modules.auth.authentication.failed_login_store as failed_login_store
import modules.auth.authentication.pending_password_change_store as pending_password_change_store
import modules.auth.authentication.principal_service as principal_service
import modules.auth.authentication.schema as authentication_schema
import modules.auth.authentication.service as authentication_service
import modules.auth.constants as auth_constants
import modules.auth.contracts as auth_contracts
import modules.auth.credentials.integration_service as credentials_integration
import modules.auth.lockout.contracts as lockout_contracts
import modules.users.users.schema as users_schema

logger = core_logger.get_logger(__name__)


def resolve_from_access_token(access_token: str, db: Session) -> auth_contracts.Principal:
    """Resolve and validate an access token against the current database state."""
    return principal_service.resolve_from_access_token(access_token, access_tokens_integration.get_token_manager(), db)


def resolve_from_api_key(raw_key: str, request: Request, db: Session) -> auth_contracts.Principal:
    """Resolve and validate an API key against the current database state."""
    return principal_service.resolve_from_api_key(raw_key, request.url.path, core_network.get_ip_address(request), db)


def clear_account_login_lockout(user_id: int) -> None:
    """Lift the account-wide sign-in lock and failure count of an account after its password was replaced.

    A credential change that follows an outage of the shared state still succeeds; the lock then ends on its own or at
    the next successful sign-in.

    Args:
        user_id: The account whose account-wide failed sign-ins are forgotten.
    """
    try:
        failed_login_store.FailedLoginAttempts(core_dependencies.get_platform_state()).reset_account(user_id)
    except lockout_contracts.AuthSecurityStoreUnavailableError:
        logger.warning("Account sign-in lock was not cleared because the shared state is unavailable")


PendingPasswordChange = pending_password_change_store.PendingPasswordChange
PendingPasswordChangeStore = pending_password_change_store.PendingPasswordChangeStore
get_pending_password_change_store = pending_password_change_store.get_pending_password_change_store


def raise_auth_security_store_unavailable(err: lockout_contracts.AuthSecurityStoreUnavailableError) -> None:
    """Answer an outage of the shared authentication state with a controlled 503.

    Args:
        err: The outage.

    Raises:
        ServiceUnavailableError: Always.
    """
    authentication_service.raise_auth_security_store_unavailable(err)


def finish_login(
    ip_address: str,
    user_agent: str,
    user: users_schema.UserRead,
    client_type: auth_constants.ClientType,
    code_challenge: str | None,
    code_challenge_method: str | None,
    password_hasher: credentials_integration.PasswordHasher,
    token_manager: access_tokens_integration.TokenManager,
    db: Session,
    *,
    mfa: bool,
    device_id: str | None,
    security_generation: int | None,
) -> authentication_schema.AuthOutcome[authentication_schema.FinishedLoginRead]:
    """Complete a verified sign-in: a web client gets tokens, a mobile client a session to exchange."""
    return authentication_service.finish_login(
        ip_address,
        user_agent,
        user,
        client_type,
        code_challenge,
        code_challenge_method,
        password_hasher,
        token_manager,
        db,
        mfa=mfa,
        device_id=device_id,
        security_generation=security_generation,
    )
