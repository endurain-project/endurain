"""Auth-owned MFA primitives and per-user MFA workflow helpers.

Module layering (where MFA logic lives):

- ``modules.auth.mfa.service`` (this module): pure TOTP/QR helpers
  (:func:`generate_totp_secret`, :func:`verify_totp`,
  :func:`generate_qr_code`) and the per-user workflow helpers that read/write
  MFA state (:func:`setup_user_mfa`, :func:`enable_user_mfa`,
  :func:`disable_user_mfa`, :func:`verify_user_mfa`,
  :func:`is_mfa_enabled_for_user`). No HTTP request/response shapes here.
- ``modules.auth.mfa.crud``: persistence for the ``users_mfa`` table.
- ``modules.auth._internal.services.mfa_workflow``: route-facing orchestration (step-up
  verification, setup-secret store handling, response/schema shaping) that
  composes the helpers in this module. Profile routes call that module, not
  this one, for end-to-end flows.
"""

from __future__ import annotations

import base64
from io import BytesIO
from typing import TYPE_CHECKING

import pyotp
import qrcode
from fastapi import HTTPException, status
from sqlalchemy.orm import Session

import core.cryptography as core_cryptography
import core.logger as core_logger
import modules.auth.mfa.backup_codes.crud as mfa_backup_codes_crud
import modules.auth.mfa.backup_codes.utils as mfa_backup_codes_utils
import modules.auth.mfa.crud as auth_mfa_crud
import modules.auth.mfa.schema as mfa_schema
import modules.users.users.utils as users_utils

logger = core_logger.get_logger(__name__)

if TYPE_CHECKING:
    import modules.auth.identity_service as auth_identity_service

# ---------------------------------------------------------------------------
# TOTP / QR-code helpers (pure, no DB)
# ---------------------------------------------------------------------------


def generate_totp_secret() -> str:
    """
    Generate random TOTP secret for MFA.

    Returns:
        Base32-encoded secret string.
    """
    return pyotp.random_base32()


def verify_totp(secret: str, token: str) -> bool:
    """
    Verify TOTP token against secret.

    Args:
        secret: Base32-encoded TOTP secret.
        token: TOTP token to verify.

    Returns:
        True if token is valid, False otherwise.
    """
    totp = pyotp.TOTP(secret)
    return totp.verify(token, valid_window=1)  # Allow 1 window tolerance


def generate_qr_code(secret: str, username: str, app_name: str = "Endurain") -> str:
    """
    Generate QR code for MFA setup.

    Args:
        secret: TOTP secret.
        username: User's username.
        app_name: Application name for MFA.

    Returns:
        Base64-encoded PNG QR code as data URI.
    """
    totp = pyotp.TOTP(secret)
    provisioning_uri = totp.provisioning_uri(name=username, issuer_name=app_name)

    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_L,
        box_size=10,
        border=4,
    )
    qr.add_data(provisioning_uri)
    qr.make(fit=True)

    img = qr.make_image(fill_color="black", back_color="white")

    buffer = BytesIO()
    img.save(buffer, format="PNG")
    buffer.seek(0)
    img_base64 = base64.b64encode(buffer.getvalue()).decode()

    return f"data:image/png;base64,{img_base64}"


# ---------------------------------------------------------------------------
# MFA workflow functions
# ---------------------------------------------------------------------------


def setup_user_mfa(user_id: int, db: Session) -> mfa_schema.MFASetupResponse:
    """
    Setup MFA for user.

    Args:
        user_id: User ID to setup MFA for.
        db: Database session.

    Returns:
        MFA setup response with secret and QR code.

    Raises:
        HTTPException: If user not found or MFA already enabled.
    """
    user = users_utils.get_user_by_id_or_404(user_id, db)

    if is_mfa_enabled_for_user(user_id, db):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="MFA is already enabled for this user",
        )

    secret = generate_totp_secret()
    qr_code = generate_qr_code(secret, user.username)

    return mfa_schema.MFASetupResponse(secret=secret, qr_code=qr_code, app_name="Endurain")


def enable_user_mfa(
    user_id: int,
    secret: str,
    mfa_code: str,
    identity_service: auth_identity_service.IdentityService,
    db: Session,
) -> list[str]:
    """
    Enable MFA for user after verification.

    Args:
        user_id: User ID to enable MFA for.
        secret: TOTP secret to verify.
        mfa_code: MFA code to verify.
        identity_service: Identity service dependency.
        db: Database session.

    Returns:
        List of generated backup codes.

    Raises:
        HTTPException: If user not found, MFA already enabled, code
            invalid, or encryption fails.
    """
    users_utils.get_user_by_id_or_404(user_id, db)

    if is_mfa_enabled_for_user(user_id, db):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="MFA is already enabled for this user",
        )

    if not verify_totp(secret, mfa_code):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid MFA code")

    encrypted_secret = core_cryptography.encrypt_token_fernet(secret)

    if not encrypted_secret:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to encrypt MFA secret",
        )

    auth_mfa_crud.update_user_mfa(user_id, db, encrypted_secret=encrypted_secret)

    backup_codes = mfa_backup_codes_crud.create_backup_codes(user_id, identity_service, db)

    return backup_codes


def disable_user_mfa(user_id: int, db: Session) -> None:
    """
    Clear MFA state for user.

    This helper does NOT verify any MFA code itself — callers
    are responsible for proving identity (e.g. via
    :func:`modules.auth._internal.services.step_up_service.verify_step_up_credentials`,
    which accepts both TOTP and backup codes for parity with login).
    Performing the check here as well would either double-charge
    a backup code or, worse, reject a backup code that step-up
    just accepted.

    Args:
        user_id: User ID to disable MFA for.
        db: Database session.

    Raises:
        HTTPException: 404 if the user is not found, 400 if MFA
            is not currently enabled.
    """
    users_utils.get_user_by_id_or_404(user_id, db)

    if not is_mfa_enabled_for_user(user_id, db):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="MFA is not enabled for this user",
        )

    auth_mfa_crud.update_user_mfa(user_id, db)
    mfa_backup_codes_crud.delete_user_backup_codes(user_id, db)


def verify_user_mfa(
    user_id: int,
    mfa_code: str,
    identity_service: auth_identity_service.IdentityService,
    db: Session,
) -> bool:
    """
    Verify MFA code for user (TOTP or backup code).

    Args:
        user_id: User ID to verify MFA for.
        mfa_code: MFA code to verify (6-digit TOTP or 8-character backup code).
        identity_service: Identity service dependency.
        db: Database session.

    Returns:
        True if code is valid, False otherwise.

    Raises:
        HTTPException: If user not found.

    Notes:
        - First tries TOTP verification (6 digits)
        - If TOTP fails and code is 9 characters (XXXX-XXXX), tries backup code
        - Backup codes are consumed on successful verification
    """
    user = users_utils.get_user_by_id_or_404(user_id, db)

    mfa_row = auth_mfa_crud.get_user_mfa_row(user.id, db)
    if not mfa_row or not mfa_row.mfa_enabled or not mfa_row.mfa_secret:
        return False

    # Normalize code (remove whitespaces in the beginning and end, uppercase)
    normalized_code = mfa_code.strip().upper()

    # Try TOTP first (6 digits)
    if len(normalized_code) == 6 and normalized_code.isdigit():
        try:
            secret = core_cryptography.decrypt_token_fernet(mfa_row.mfa_secret)
            if not secret:
                logger.error("Failed to decrypt MFA secret")
                return False

            if verify_totp(secret, normalized_code):
                logger.debug(f"User {user_id} verified MFA with TOTP")
                return True
        except ValueError as err:
            # Covers binascii.Error (non-base32 secret) and any other value
            # error from the pyotp stack; treat as verification failure.
            logger.error(f"Error in TOTP verification: {err}", exc_info=err)
            return False
        # Unexpected errors (I/O, crypto infrastructure failures, etc.) are
        # intentionally left unhandled so they surface to the global handler
        # rather than being silently swallowed as a False return.

    # Try backup code (9 alphanumeric characters with dash XXXX-XXXX)
    elif (
        len(normalized_code) == 9
        and normalized_code[4] == "-"
        and mfa_backup_codes_utils.verify_and_consume_backup_code(
            user_id,
            normalized_code,
            identity_service,
            db,
        )
    ):
        return True

    # Invalid format or code didn't match
    return False


def is_mfa_enabled_for_user(user_id: int, db: Session) -> bool:
    """
    Check if MFA is enabled for user.

    Args:
        user_id: User ID to check.
        db: Database session.

    Returns:
        True if MFA is enabled, False otherwise.
    """
    try:
        user = users_utils.get_user_by_id_or_404(user_id, db)
    except HTTPException as err:
        if err.status_code == status.HTTP_404_NOT_FOUND:
            return False
        raise

    if not user:
        return False
    mfa_row = auth_mfa_crud.get_user_mfa_row(user.id, db)
    return bool(mfa_row and mfa_row.mfa_enabled and mfa_row.mfa_secret is not None)
