"""Account-security operations used by the users module."""

from sqlalchemy.orm import Session

import core.dependencies as core_dependencies
import core.pagination as core_pagination
import modules.auth.account_security.account_security_service as account_security_service
import modules.auth.account_security.identity_link_service as identity_link_service
import modules.auth.account_security.mfa_workflow_service as mfa_workflow_service
import modules.auth.account_security.step_up_service as step_up_service
import modules.auth.account_security.step_up_store as step_up_store_module
import modules.auth.identity_provider_links.schema as identity_links_schema
import modules.auth.identity_providers.constants as identity_providers_constants
import modules.auth.mfa.schema as mfa_schema
import modules.auth.schema as auth_schema

StepUpStore = step_up_store_module.StepUpStore


def get_step_up_attempts(state: core_dependencies.PlatformState) -> StepUpStore:
    """Resolve the shared account-security step-up attempt store."""
    return step_up_store_module.get_step_up_attempts(state)


def verify_step_up(
    step_up: auth_schema.StepUpVerification,
    user_id: int,
    session_id: str,
    action: identity_providers_constants.StepUpAction,
    step_up_store: step_up_store_module.StepUpStore,
    db: Session,
) -> None:
    """Require fresh proof of identity for a sensitive account operation."""
    step_up_service.verify_step_up_credentials(
        user_id,
        step_up.current_password,
        step_up.mfa_code,
        step_up_store,
        db,
        idp_reauth=step_up.idp_reauth,
        session_id=session_id,
        action=action,
    )


def change_own_password(
    user_id: int,
    current_password: str | None,
    new_password: str,
    mfa_code: str | None,
    step_up_store: step_up_store_module.StepUpStore,
    db: Session,
    *,
    revoke_other_sessions: bool,
    current_session_id: str,
) -> None:
    """Stage a change of a user's password after step-up verification."""
    account_security_service.stage_change_own_password(
        user_id,
        current_password,
        new_password,
        mfa_code,
        step_up_store,
        db,
        revoke_other_sessions=revoke_other_sessions,
        current_session_id=current_session_id,
    )


def change_managed_user_password(
    user_id: int,
    new_password: str,
    db: Session,
) -> None:
    """Stage a managed user's password change and the revocation of their auth state."""
    account_security_service.change_managed_user_password(user_id, new_password, db)


def reset_managed_user_mfa(user_id: int, db: Session) -> None:
    """Stage a managed user's MFA reset and the end of all of their sessions."""
    account_security_service.reset_managed_user_mfa(user_id, db)


def require_managed_user_password_change(user_id: int, db: Session) -> None:
    """Stage the requirement that a managed user replace their password at the next sign-in."""
    account_security_service.require_managed_user_password_change(user_id, db)


def delete_all_user_sessions(user_id: int, db: Session) -> None:
    """Stage the revocation of every session belonging to a user."""
    account_security_service.delete_all_user_sessions(user_id, db)


def delete_other_user_sessions(user_id: int, current_session_id: str, db: Session) -> int:
    """Stage the revocation of a user's sessions except the current one."""
    return account_security_service.stage_delete_other_user_sessions(user_id, current_session_id, db)


def get_mfa_status(user_id: int, db: Session) -> mfa_schema.MFAStatusRead:
    """Return whether MFA is enabled for a user."""
    return mfa_workflow_service.get_mfa_status(user_id, db)


def get_user_identity_provider_links(
    user_id: int,
    page: core_pagination.PageParams,
    db: Session,
) -> identity_links_schema.IdentityProviderLinkPage:
    """Return one page of a user's enriched identity-provider links."""
    return identity_link_service.get_user_identity_provider_links(user_id, page, db)


def admin_delete_identity_provider_link(user_id: int, idp_id: int, db: Session) -> None:
    """Stage the unlinking of an identity provider from a user as an administrator."""
    identity_link_service.admin_delete_identity_provider_link(user_id, idp_id, db)
