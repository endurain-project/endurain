"""First-run onboarding: report whether it is needed and create the first administrator."""

from sqlalchemy.orm import Session

import core.exceptions as core_exceptions
import core.logger as core_logger
import modules.auth.credentials.contracts as credentials_contracts
import modules.auth.onboarding.schema as onboarding_schema
import modules.auth.onboarding.token_store as onboarding_token_store
import modules.users.users.integration_service as users_integration
import modules.users.users.schema as users_schema

logger = core_logger.get_logger(__name__)


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
) -> users_schema.UsersRead:
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
        PasswordPolicyError: If the password fails the administrator policy.
        ServiceUnavailableError: If the token store is unavailable.
    """
    if users_integration.any_user_exists(db):
        logger.warning("Onboarding refused: an account already exists")
        raise core_exceptions.ConflictError("An account already exists")
    if not store.exists(request.token):
        logger.warning("Onboarding refused: the setup token is unknown, expired or used")
        raise core_exceptions.InvalidInputError("Invalid or expired setup token")

    try:
        admin = users_integration.stage_first_admin(request, db)
    except core_exceptions.ConflictError:
        db.rollback()
        logger.warning("Onboarding refused: an account was created first")
        raise
    except core_exceptions.InvalidInputError as err:
        db.rollback()
        logger.warning("Onboarding refused: the password does not meet the policy")
        raise credentials_contracts.PasswordPolicyError(err.detail) from err

    if not store.claim(request.token):
        db.rollback()
        logger.warning("Onboarding refused: the setup token was used by another request")
        raise core_exceptions.InvalidInputError("Invalid or expired setup token")

    db.commit()
    logger.info("First administrator created by onboarding", extra=core_logger.context(user_id=admin.id))
    return admin
