"""MFA operations exposed to auth peers and application entrypoints."""

from jasil.providers import StateProvider
from sqlalchemy.orm import Session

import core.dependencies as core_dependencies
import core.logger as core_logger
import modules.auth.credentials.contracts as credentials_contracts
import modules.auth.lockout.contracts as lockout_contracts
import modules.auth.mfa.contracts as mfa_contracts
import modules.auth.mfa.crud as mfa_crud
import modules.auth.mfa.pending_login_store as pending_login_store
import modules.auth.mfa.schema as mfa_schema
import modules.auth.mfa.service as mfa_service
import modules.auth.mfa.totp_replay_store as mfa_totp_replay_store

logger = core_logger.get_logger(__name__)


def is_mfa_enabled_for_user(user_id: int, db: Session) -> bool:
    """Return whether MFA is enabled for a user."""
    return mfa_service.is_mfa_enabled_for_user(user_id, db)


def verify_user_mfa(
    user_id: int,
    mfa_code: str,
    password_verifier: credentials_contracts.SupportsVerifyPassword,
    db: Session,
    *,
    replay_guard: mfa_contracts.SupportsClaimTotpStep,
) -> bool:
    """Verify a TOTP or backup code for a user; a TOTP step is accepted once."""
    return mfa_service.verify_user_mfa(user_id, mfa_code, password_verifier, db, replay_guard=replay_guard)


def claim_totp_step(state: StateProvider, user_id: int, step: int) -> bool:
    """Record an accepted TOTP step as used; False when it already was."""
    return mfa_totp_replay_store.claim_totp_step(state, user_id, step)


def setup_user_mfa(user_id: int, db: Session) -> mfa_schema.MFASetupRead:
    """Create setup material for a user's TOTP secret."""
    return mfa_service.setup_user_mfa(user_id, db)


def enable_user_mfa(
    user_id: int,
    secret: str,
    mfa_code: str,
    password_hasher: credentials_contracts.SupportsHashPassword,
    db: Session,
    *,
    replay_guard: mfa_contracts.SupportsClaimTotpStep,
) -> list[str]:
    """Enable MFA and create replacement backup codes; the enrolment TOTP step is accepted once."""
    return mfa_service.enable_user_mfa(user_id, secret, mfa_code, password_hasher, db, replay_guard=replay_guard)


def disable_user_mfa(user_id: int, db: Session) -> None:
    """Disable MFA and remove backup codes."""
    mfa_service.disable_user_mfa(user_id, db)


def clear_mfa_account_lockout(username: str) -> None:
    """Lift the account-wide MFA sign-in lock and wrong-code count of a username after its second factor changed.

    A change that follows an outage of the shared state still succeeds; the lock then ends on its own or at the next
    successful MFA sign-in.

    Args:
        username: The username whose account-wide wrong MFA codes are forgotten.
    """
    try:
        pending_login_store.PendingMFALogin(core_dependencies.get_platform_state()).reset_account(username)
    except lockout_contracts.AuthSecurityStoreUnavailableError:
        logger.warning("Account MFA sign-in lock was not cleared because the shared state is unavailable")


def get_mfa_enabled_for_users(user_ids: list[int], db: Session) -> dict[int, bool]:
    """Return enabled MFA state for the supplied users in one query."""
    return mfa_crud.get_mfa_enabled_for_users(user_ids, db)


def create_users_mfa_row(user_id: int, db: Session) -> mfa_contracts.MFAStateRead:
    """Stage the default disabled MFA state for a new user."""
    return mfa_crud.create_users_mfa_row(user_id, db)
