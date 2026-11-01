"""Auth-owned MFA primitives and per-user MFA workflow helpers.

Module layering (where MFA logic lives):

- ``modules.auth.mfa.service`` (this module): pure TOTP/QR helpers
  (:func:`generate_totp_secret`, :func:`verify_totp`,
  :func:`generate_qr_code`) and the per-user workflow helpers that read/write
  MFA state (:func:`setup_user_mfa`, :func:`enable_user_mfa`,
  :func:`disable_user_mfa`, :func:`verify_user_mfa`,
  :func:`is_mfa_enabled_for_user`). No HTTP request/response shapes here.
- ``modules.auth.mfa.crud``: persistence for the ``users_mfa`` table.
- ``modules.auth.account_security.mfa_workflow_service``: route-facing orchestration (step-up
  verification, setup-secret store handling, response/schema shaping) that
  composes the helpers in this module. Profile routes call that module, not
  this one, for end-to-end flows.
"""

from __future__ import annotations

import base64
from datetime import UTC, datetime
from io import BytesIO

import pyotp
import qrcode
from sqlalchemy.orm import Session

import core.cryptography as core_cryptography
import core.exceptions as core_exceptions
import core.logger as core_logger
import modules.auth.credentials.contracts as credentials_contracts
import modules.auth.mfa.contracts as mfa_contracts
import modules.auth.mfa.crud as auth_mfa_crud
import modules.auth.mfa.schema as mfa_schema
import modules.auth.mfa.totp_replay_store as mfa_totp_replay_store
import modules.auth.mfa_backup_codes.integration_service as mfa_backup_codes_integration
import modules.users.users.integration_service as users_integration

logger = core_logger.get_logger(__name__)

# ---------------------------------------------------------------------------
# TOTP / QR-code helpers (pure, no DB)
# ---------------------------------------------------------------------------


def generate_totp_secret() -> str:
    """Generate random TOTP secret for MFA.

    Returns:
        Base32-encoded secret string.
    """
    return pyotp.random_base32()


def verify_totp(secret: str, token: str) -> bool:
    """Verify TOTP token against secret.

    Args:
        secret: Base32-encoded TOTP secret.
        token: TOTP token to verify.

    Returns:
        True if token is valid, False otherwise.
    """
    return mfa_totp_replay_store.matching_totp_step(secret, token, datetime.now(UTC)) is not None


def generate_qr_code(secret: str, username: str, app_name: str = "Endurain") -> str:
    """Generate QR code for MFA setup.

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


def setup_user_mfa(user_id: int, db: Session) -> mfa_schema.MFASetupRead:
    """Setup MFA for user.

    Args:
        user_id: User ID to setup MFA for.
        db: Database session.

    Returns:
        MFA setup response with secret and QR code.

    Raises:
        InvalidInputError: If MFA is already enabled.
    """
    user = users_integration.require_user(user_id, db)

    if is_mfa_enabled_for_user(user_id, db):
        raise core_exceptions.InvalidInputError("MFA is already enabled for this user")

    secret = generate_totp_secret()
    qr_code = generate_qr_code(secret, user.username)

    return mfa_schema.MFASetupRead(secret=secret, qr_code=qr_code, app_name="Endurain")


def enable_user_mfa(
    user_id: int,
    secret: str,
    mfa_code: str,
    password_hasher: credentials_contracts.SupportsHashPassword,
    db: Session,
) -> list[str]:
    """Enable MFA for user after verification.

    Args:
        user_id: User ID to enable MFA for.
        secret: TOTP secret to verify.
        mfa_code: MFA code to verify.
        password_hasher: Hasher used to store backup codes.
        db: Database session.

    Returns:
        List of generated backup codes.

    Raises:
        InvalidInputError: If MFA is already enabled or the code is invalid.
        ProcessingError: If the secret cannot be encrypted.

    Notes:
        Stages the change; the caller commits.
    """
    users_integration.require_user(user_id, db)

    if is_mfa_enabled_for_user(user_id, db):
        raise core_exceptions.InvalidInputError("MFA is already enabled for this user")

    if not verify_totp(secret, mfa_code):
        raise core_exceptions.InvalidMfaCodeError()

    encrypted_secret = core_cryptography.encrypt_token_fernet(secret)

    if not encrypted_secret:
        raise core_exceptions.ProcessingError("Failed to encrypt MFA secret")

    auth_mfa_crud.update_user_mfa(user_id, db, encrypted_secret=encrypted_secret)

    return mfa_backup_codes_integration.create_backup_codes(user_id, password_hasher, db)


def disable_user_mfa(user_id: int, db: Session) -> None:
    """Clear MFA state for user.

    This helper does NOT verify any MFA code itself — callers
    are responsible for proving identity (e.g. via
    :func:`modules.auth.account_security.step_up_service.verify_step_up_credentials`,
    which accepts both TOTP and backup codes for parity with login).
    Performing the check here as well would either double-charge
    a backup code or, worse, reject a backup code that step-up
    just accepted.

    Args:
        user_id: User ID to disable MFA for.
        db: Database session.

    Raises:
        NotFoundError if the user is not found, InvalidInputError if MFA
            is not currently enabled.

    Notes:
        Stages the change; the caller commits.
    """
    users_integration.require_user(user_id, db)

    if not is_mfa_enabled_for_user(user_id, db):
        raise core_exceptions.InvalidInputError("MFA is not enabled for this user")

    auth_mfa_crud.update_user_mfa(user_id, db)
    mfa_backup_codes_integration.delete_user_backup_codes(user_id, db)


def verify_user_mfa(
    user_id: int,
    mfa_code: str,
    password_verifier: credentials_contracts.SupportsVerifyPassword,
    db: Session,
    *,
    replay_guard: mfa_contracts.SupportsClaimTotpStep,
) -> bool:
    """Verify MFA code for user (TOTP or backup code).

    Args:
        user_id: User ID to verify MFA for.
        mfa_code: MFA code to verify (6-digit TOTP or 8-character backup code).
        password_verifier: Verifier used to check backup codes.
        db: Database session.
        replay_guard: Records each accepted TOTP step, so a code works once.

    Returns:
        True if code is valid, False otherwise.

    Raises:
        NotFoundError: If user not found.

    Notes:
        - First tries TOTP verification (6 digits)
        - If TOTP fails and code is 9 characters (XXXX-XXXX), tries backup code
        - A backup code is consumed (staged) on successful verification; the caller commits
    """
    user = users_integration.require_user(user_id, db)

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

            step = mfa_totp_replay_store.matching_totp_step(secret, normalized_code, datetime.now(UTC))
            if step is not None:
                if not replay_guard.claim_totp_step(user_id, step):
                    logger.warning("Refused a replayed TOTP code", extra=core_logger.context(user_id=user_id))
                    return False
                logger.debug("User verified MFA with TOTP", extra=core_logger.context(user_id=user_id))
                return True
        except ValueError as err:
            # Covers binascii.Error (non-base32 secret) and any other value
            # error from the pyotp stack; treat as verification failure.
            logger.error("Error in TOTP verification", exc_info=err, extra=core_logger.context(user_id=user_id))
            return False
        # Unexpected errors (I/O, crypto infrastructure failures, etc.) are
        # intentionally left unhandled so they surface to the global handler
        # rather than being silently swallowed as a False return.

    # Try backup code (9 alphanumeric characters with dash XXXX-XXXX)
    elif (
        len(normalized_code) == 9
        and normalized_code[4] == "-"
        and mfa_backup_codes_integration.verify_and_consume_backup_code(
            user_id,
            normalized_code,
            password_verifier,
            db,
        )
    ):
        return True

    # Invalid format or code didn't match
    return False


def is_mfa_enabled_for_user(user_id: int, db: Session) -> bool:
    """Check if MFA is enabled for user.

    Args:
        user_id: User ID to check.
        db: Database session.

    Returns:
        True if MFA is enabled, False otherwise.
    """
    try:
        user = users_integration.require_user(user_id, db)
    except core_exceptions.NotFoundError:
        return False

    if not user:
        return False
    mfa_row = auth_mfa_crud.get_user_mfa_row(user.id, db)
    return bool(mfa_row and mfa_row.mfa_enabled and mfa_row.mfa_secret is not None)
