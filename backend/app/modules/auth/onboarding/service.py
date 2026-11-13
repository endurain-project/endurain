"""First-run onboarding: report whether it is needed and create the first administrator."""

import jasil.audit as jasil_audit
from sqlalchemy.orm import Session

import core.exceptions as core_exceptions
import core.logger as core_logger
import modules.auth.credentials.contracts as credentials_contracts
import modules.auth.credentials.integration_service as credentials_integration
import modules.auth.onboarding.audit_actions as onboarding_audit_actions
import modules.auth.onboarding.schema as onboarding_schema
import modules.auth.onboarding.token_store as onboarding_token_store
import modules.server_settings.integration_service as server_settings_integration
import modules.users.users.integration_service as users_integration
import modules.users.users.schema as users_schema

logger = core_logger.get_logger(__name__)


def _record_refusal(reason: onboarding_audit_actions.OnboardingRefusalReason) -> None:
    """Record a refused onboarding attempt, with its reason and never the setup token."""
    jasil_audit.record_detached(
        onboarding_audit_actions.ONBOARDING_REFUSE,
        outcome=jasil_audit.Outcome.DENIED,
        details=onboarding_audit_actions.OnboardingRefusalDetails(reason=reason),
    )


def get_onboarding_status(db: Session) -> onboarding_schema.OnboardingStatusRead:
    """Report whether the installation still needs its first administrator.

    Args:
        db: Database session.

    Returns:
        The status, which is required exactly while no account exists.
    """
    return onboarding_schema.OnboardingStatusRead(onboarding_required=not users_integration.any_user_exists(db))


def complete_onboarding(
    request: onboarding_schema.OnboardingCreate,
    store: onboarding_token_store.OnboardingTokenStore,
    db: Session,
) -> users_schema.UserRead:
    """Create the first administrator when the setup token is valid and no account exists.

    The cheap refusals come first, so a request that cannot succeed costs no password hashing. The token is
    consumed only after the account is staged, so a weak password does not burn it, and the account commits only
    after this request holds the token.

    Args:
        request: The setup token and the administrator's details.
        store: The setup-token store.
        db: Database session.

    Returns:
        The created administrator.

    Raises:
        ConflictError: If an account already exists.
        InvalidInputError: If the setup token is unknown, expired or already used.
        PasswordPolicyError: If the password fails the administrator policy or is breached.
        ServiceUnavailableError: If the token store is unavailable.
    """
    reasons = onboarding_audit_actions.OnboardingRefusalReason
    if users_integration.any_user_exists(db):
        logger.warning("Onboarding refused: an account already exists")
        _record_refusal(reasons.ACCOUNT_EXISTS)
        raise core_exceptions.ConflictError("An account already exists")
    if not store.exists(request.token):
        logger.warning("Onboarding refused: the setup token is unknown, expired or used")
        _record_refusal(reasons.INVALID_TOKEN)
        raise core_exceptions.InvalidInputError("Invalid or expired setup token")
    # The breach check is a network call, so it runs before the account is staged.
    try:
        credentials_integration.reject_breached_password(
            server_settings_integration.get_server_settings(db), request.password, db
        )
    except credentials_contracts.PasswordPolicyError:
        logger.warning("Onboarding refused: the password is breached")
        _record_refusal(reasons.PASSWORD_POLICY)
        raise

    try:
        admin = users_integration.stage_first_admin(request, db)
    except core_exceptions.ConflictError:
        db.rollback()
        logger.warning("Onboarding refused: an account was created first")
        _record_refusal(reasons.ACCOUNT_EXISTS)
        raise
    except credentials_contracts.PasswordPolicyError:
        db.rollback()
        logger.warning("Onboarding refused: the password does not meet the policy")
        _record_refusal(reasons.PASSWORD_POLICY)
        raise

    if not store.claim(request.token):
        db.rollback()
        logger.warning("Onboarding refused: the setup token was used by another request")
        _record_refusal(reasons.INVALID_TOKEN)
        raise core_exceptions.InvalidInputError("Invalid or expired setup token")

    db.commit()
    logger.info("First administrator created by onboarding", extra=core_logger.context(user_id=str(admin.id)))
    return admin
