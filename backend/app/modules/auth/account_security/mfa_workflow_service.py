"""Route-facing MFA workflow orchestration exposed to profile routes.

Module layering (where MFA logic lives):

- ``modules.auth.account_security.mfa_workflow_service`` (this module): the workflow facade profile
  routes call. It composes lower-level helpers and owns step-up verification,
  the pending setup-secret store, and response/schema shaping.
- ``modules.auth.mfa.service``: pure TOTP/QR helpers plus the per-user state helpers
  (setup/enable/disable/verify) this module orchestrates.
- ``modules.auth.mfa.crud``: persistence for the ``users_mfa`` table.

Profile routes depend on this module, never on ``modules.auth.mfa.*`` directly.
"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy.orm import Session

import core.exceptions as core_exceptions
import core.logger as core_logger
import modules.auth.account_security.step_up_service as step_up_service
import modules.auth.account_security.step_up_store as account_security_step_up_store
import modules.auth.credentials.integration_service as credentials_integration
import modules.auth.identity_providers.constants as identity_providers_constants
import modules.auth.mfa.integration_service as mfa_integration
import modules.auth.mfa.schema as mfa_schema
import modules.auth.mfa_backup_codes.integration_service as mfa_backup_codes_integration
import modules.auth.mfa_backup_codes.schema as mfa_backup_codes_schema
import modules.users.users.integration_service as users_integration
import modules.users.users.schema as users_schema
from modules.auth.mfa.contracts import MFASecretStoreBackend

logger = core_logger.get_logger(__name__)


def get_mfa_status(
    token_user_id: int,
    db: Session,
) -> mfa_schema.MFAStatusRead:
    """Return whether MFA is enabled for the user."""
    is_enabled = mfa_integration.is_mfa_enabled_for_user(token_user_id, db)
    return mfa_schema.MFAStatusRead(mfa_enabled=is_enabled)


def get_mfa_enabled_for_users(
    user_ids: list[int],
    db: Session,
) -> dict[int, bool]:
    """Return MFA-enabled state per user ID in a single query."""
    return mfa_integration.get_mfa_enabled_for_users(user_ids, db)


def get_backup_code_status(
    token_user_id: int,
    db: Session,
) -> mfa_backup_codes_schema.MFABackupCodeStatusRead:
    """Retrieve MFA backup code status for the authenticated user."""
    codes = mfa_backup_codes_integration.get_user_backup_codes(token_user_id, db)

    if not codes:
        return mfa_backup_codes_schema.MFABackupCodeStatusRead(
            has_codes=False,
            total=0,
            unused=0,
            used=0,
            created_at=None,
        )

    unused = sum(1 for code in codes if not code.used)
    used = sum(1 for code in codes if code.used)
    created_at = codes[0].created_at if codes else None

    return mfa_backup_codes_schema.MFABackupCodeStatusRead(
        has_codes=True,
        total=len(codes),
        unused=unused,
        used=used,
        created_at=created_at,
    )


def setup_mfa(
    token_user_id: int,
    mfa_secret_store: MFASecretStoreBackend,
    db: Session,
) -> mfa_schema.MFASetupRead:
    """Create MFA setup material and store pending setup secret."""
    response = mfa_integration.setup_user_mfa(token_user_id, db)
    db.commit()
    mfa_secret_store.add_secret(token_user_id, response.secret)
    logger.info("MFA setup initialized", extra=core_logger.context(user_id=token_user_id))
    return response


def enable_mfa(
    request: mfa_schema.MFASetupRequest,
    token_user_id: int,
    session_id: str,
    step_up_store: account_security_step_up_store.StepUpStore,
    mfa_secret_store: MFASecretStoreBackend,
    db: Session,
) -> mfa_schema.MFAEnableRead:
    """Enable MFA using pending secret and verification code.

    The pending setup is checked before step-up, so a request without one does not spend an identity-provider
    step-up ticket.
    """
    secret = mfa_secret_store.get_secret(token_user_id)
    if not secret:
        raise core_exceptions.InvalidInputError("No MFA setup in progress. Please run setup first.")

    step_up_service.verify_step_up_credentials(
        token_user_id,
        request.current_password,
        None,
        step_up_store,
        db,
        idp_reauth=request.idp_reauth,
        session_id=session_id,
        action=identity_providers_constants.StepUpAction.MFA_ENABLE,
    )

    try:
        backup_codes = mfa_integration.enable_user_mfa(
            token_user_id,
            secret,
            request.mfa_code,
            credentials_integration.get_password_hasher(),
            db,
        )
        db.commit()
        mfa_secret_store.delete_secret(token_user_id)
        logger.info(
            "User <token_user_id> enabled MFA (step-up verified)",
            extra=core_logger.context(token_user_id=token_user_id),
        )
        return mfa_schema.MFAEnableRead(message="MFA enabled successfully", backup_codes=backup_codes)
    except core_exceptions.InvalidMfaCodeError:
        raise
    except core_exceptions.DomainError:
        mfa_secret_store.delete_secret(token_user_id)
        raise


def disable_mfa(
    request: mfa_schema.MFADisableRequest,
    token_user_id: int,
    session_id: str,
    step_up_store: account_security_step_up_store.StepUpStore,
    db: Session,
) -> mfa_schema.MFADisableRead:
    """Disable MFA after step-up verification."""
    step_up_service.verify_step_up_credentials(
        token_user_id,
        request.current_password,
        request.mfa_code,
        step_up_store,
        db,
        idp_reauth=request.idp_reauth,
        session_id=session_id,
        action=identity_providers_constants.StepUpAction.MFA_DISABLE,
    )
    mfa_integration.disable_user_mfa(token_user_id, db)
    db.commit()
    logger.info(
        "User <token_user_id> disabled MFA (step-up verified)", extra=core_logger.context(token_user_id=token_user_id)
    )
    return mfa_schema.MFADisableRead(message="MFA disabled successfully")


def verify_mfa(
    request: mfa_schema.MFARequest,
    token_user_id: int,
    step_up_store: account_security_step_up_store.StepUpStore,
    db: Session,
) -> mfa_schema.MFAVerifyRead:
    """Verify an MFA code for the authenticated user; a TOTP step is accepted once."""
    if not step_up_service.verify_mfa_code(token_user_id, request.mfa_code, step_up_store, db):
        raise core_exceptions.InvalidMfaCodeError()

    db.commit()
    logger.info("MFA code verified", extra=core_logger.context(user_id=token_user_id))
    return mfa_schema.MFAVerifyRead(message="MFA code verified successfully")


def generate_backup_codes(
    step_up: users_schema.StepUpVerification,
    token_user_id: int,
    session_id: str,
    step_up_store: account_security_step_up_store.StepUpStore,
    db: Session,
) -> mfa_backup_codes_schema.MFABackupCodesRead:
    """Generate new backup codes for an MFA-enabled account."""
    user = users_integration.get_user(token_user_id, db)

    if not user:
        raise core_exceptions.NotFoundError("User not found")

    if not mfa_integration.is_mfa_enabled_for_user(token_user_id, db):
        raise core_exceptions.InvalidInputError("MFA must be enabled to generate backup codes")

    step_up_service.verify_step_up_credentials(
        token_user_id,
        step_up.current_password,
        step_up.mfa_code,
        step_up_store,
        db,
        idp_reauth=step_up.idp_reauth,
        session_id=session_id,
        action=identity_providers_constants.StepUpAction.MFA_BACKUP_CODES,
    )

    codes = mfa_backup_codes_integration.create_backup_codes(
        token_user_id,
        credentials_integration.get_password_hasher(),
        db,
    )
    db.commit()

    logger.info("User <id> generated MFA backup codes (step-up verified)", extra=core_logger.context(id=user.id))

    return mfa_backup_codes_schema.MFABackupCodesRead(
        codes=codes,
        created_at=datetime.now(UTC),
    )
