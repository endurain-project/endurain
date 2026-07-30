"""Route-facing MFA workflow orchestration exposed to profile routes.

Module layering (where MFA logic lives):

- ``auth.services.mfa_workflow`` (this module): the workflow facade profile
  routes call. It composes lower-level helpers and owns step-up verification,
  the pending setup-secret store, and response/schema shaping.
- ``auth.mfa.service``: pure TOTP/QR helpers plus the per-user state helpers
  (setup/enable/disable/verify) this module orchestrates.
- ``auth.mfa.crud``: persistence for the ``users_mfa`` table.

Profile routes depend on this module, never on ``auth.mfa.*`` directly.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

import auth.mfa.backup_codes.crud as mfa_backup_codes_crud
import auth.mfa.backup_codes.schema as mfa_backup_codes_schema
import auth.mfa.crud as mfa_crud
import auth.mfa.schema as mfa_schema
import auth.mfa.service as mfa_service
import auth.security_stores as auth_security_stores
import auth.services.step_up_service as step_up_service
import core.logger as core_logger
import users.users.crud as users_crud
import users.users.schema as users_schema
from auth.mfa.setup_store import MFASecretStoreBackend

if TYPE_CHECKING:
    from auth.identity_service import IdentityService


def get_mfa_status(
    token_user_id: int,
    db: Session,
) -> mfa_schema.MFAStatusResponse:
    """Return whether MFA is enabled for the user."""
    is_enabled = mfa_service.is_mfa_enabled_for_user(token_user_id, db)
    return mfa_schema.MFAStatusResponse(mfa_enabled=is_enabled)


def get_mfa_enabled_for_users(
    user_ids: list[int],
    db: Session,
) -> dict[int, bool]:
    """Return MFA-enabled state per user ID in a single query."""
    return mfa_crud.get_mfa_enabled_for_users(user_ids, db)


def get_backup_code_status(
    token_user_id: int,
    db: Session,
) -> mfa_backup_codes_schema.MFABackupCodeStatus:
    """Retrieve MFA backup code status for the authenticated user."""
    codes = mfa_backup_codes_crud.get_user_backup_codes(token_user_id, db)

    if not codes:
        return mfa_backup_codes_schema.MFABackupCodeStatus(
            has_codes=False,
            total=0,
            unused=0,
            used=0,
            created_at=None,
        )

    unused = sum(1 for code in codes if not code.used)
    used = sum(1 for code in codes if code.used)
    created_at = codes[0].created_at if codes else None

    return mfa_backup_codes_schema.MFABackupCodeStatus(
        has_codes=True,
        total=len(codes),
        unused=unused,
        used=used,
        created_at=created_at,
    )


def setup_mfa(
    token_user_id: int,
    db: Session,
    mfa_secret_store: MFASecretStoreBackend,
) -> mfa_schema.MFASetupResponse:
    """Create MFA setup material and store pending setup secret."""
    response = mfa_service.setup_user_mfa(token_user_id, db)
    mfa_secret_store.add_secret(token_user_id, response.secret)
    return response


def enable_mfa(
    request: mfa_schema.MFASetupRequest,
    token_user_id: int,
    identity_service: IdentityService,
    step_up_store: auth_security_stores.StepUpStore,
    db: Session,
    mfa_secret_store: MFASecretStoreBackend,
) -> dict:
    """Enable MFA using pending secret and verification code."""
    step_up_service.verify_step_up_credentials(
        token_user_id,
        request.current_password,
        None,
        identity_service,
        step_up_store,
        db,
    )

    secret = mfa_secret_store.get_secret(token_user_id)
    if not secret:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No MFA setup in progress. Please run setup first.",
        )

    try:
        backup_codes = mfa_service.enable_user_mfa(
            token_user_id,
            secret,
            request.mfa_code,
            identity_service,
            db,
        )
        mfa_secret_store.delete_secret(token_user_id)
        core_logger.print_to_log(
            f"User {token_user_id} enabled MFA (step-up verified)",
            "info",
        )
        return {
            "message": "MFA enabled successfully",
            "backup_codes": backup_codes,
        }
    except HTTPException as exc:
        if not (exc.status_code == status.HTTP_400_BAD_REQUEST and exc.detail == "Invalid MFA code"):
            mfa_secret_store.delete_secret(token_user_id)
        raise


def disable_mfa(
    request: mfa_schema.MFADisableRequest,
    token_user_id: int,
    identity_service: IdentityService,
    step_up_store: auth_security_stores.StepUpStore,
    db: Session,
) -> dict:
    """Disable MFA after step-up verification."""
    step_up_service.verify_step_up_credentials(
        token_user_id,
        request.current_password,
        request.mfa_code,
        identity_service,
        step_up_store,
        db,
    )
    mfa_service.disable_user_mfa(token_user_id, db)
    core_logger.print_to_log(
        f"User {token_user_id} disabled MFA (step-up verified)",
        "info",
    )
    return {"message": "MFA disabled successfully"}


def verify_mfa(
    request: mfa_schema.MFARequest,
    token_user_id: int,
    identity_service: IdentityService,
    db: Session,
) -> dict:
    """Verify an MFA code for the authenticated user."""
    is_valid = mfa_service.verify_user_mfa(
        token_user_id,
        request.mfa_code,
        identity_service,
        db,
    )
    if not is_valid:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid MFA code",
        )

    return {"message": "MFA code verified successfully"}


def generate_backup_codes(
    step_up: users_schema.StepUpVerification,
    token_user_id: int,
    identity_service: IdentityService,
    step_up_store: auth_security_stores.StepUpStore,
    db: Session,
) -> mfa_backup_codes_schema.MFABackupCodesResponse:
    """Generate new backup codes for an MFA-enabled account."""
    user = users_crud.get_user_by_id(token_user_id, db)

    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )

    if not mfa_service.is_mfa_enabled_for_user(token_user_id, db):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="MFA must be enabled to generate backup codes",
        )

    step_up_service.verify_step_up_credentials(
        token_user_id,
        step_up.current_password,
        step_up.mfa_code,
        identity_service,
        step_up_store,
        db,
    )

    codes = mfa_backup_codes_crud.create_backup_codes(
        token_user_id,
        identity_service,
        db,
    )

    core_logger.print_to_log(
        f"User {user.id} generated MFA backup codes (step-up verified)",
        "info",
    )

    return mfa_backup_codes_schema.MFABackupCodesResponse(
        codes=codes,
        created_at=datetime.now(UTC),
    )
