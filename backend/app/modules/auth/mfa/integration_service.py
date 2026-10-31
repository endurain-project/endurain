"""MFA operations exposed to auth peers and application entrypoints."""

from jasil.providers import StateProvider
from sqlalchemy.orm import Session

import core.dependencies as core_dependencies
import modules.auth.credentials.contracts as credentials_contracts
import modules.auth.mfa.contracts as mfa_contracts
import modules.auth.mfa.crud as mfa_crud
import modules.auth.mfa.pending_login_store as pending_login_store
import modules.auth.mfa.schema as mfa_schema
import modules.auth.mfa.service as mfa_service
import modules.auth.mfa.totp_replay_store as mfa_totp_replay_store


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
) -> list[str]:
    """Enable MFA and create replacement backup codes."""
    return mfa_service.enable_user_mfa(user_id, secret, mfa_code, password_hasher, db)


def disable_user_mfa(user_id: int, db: Session) -> None:
    """Disable MFA and remove backup codes."""
    mfa_service.disable_user_mfa(user_id, db)


def get_mfa_enabled_for_users(user_ids: list[int], db: Session) -> dict[int, bool]:
    """Return enabled MFA state for the supplied users in one query."""
    return mfa_crud.get_mfa_enabled_for_users(user_ids, db)


def create_users_mfa_row(user_id: int, db: Session) -> mfa_contracts.MFAStateRead:
    """Stage the default disabled MFA state for a new user."""
    return mfa_crud.create_users_mfa_row(user_id, db)


def clear_pending_mfa_for_user(user_id: int) -> int:
    """Clear pending MFA login challenges after a credential change."""
    return pending_login_store.clear_pending_mfa_for_user(core_dependencies.get_platform_state(), user_id)
