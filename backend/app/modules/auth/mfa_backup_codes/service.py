"""Utility helpers for MFA backup codes."""

from __future__ import annotations

import secrets

import jasil.audit as jasil_audit
from sqlalchemy.orm import Session

import core.exceptions as core_exceptions
import modules.auth.credentials.contracts as credentials_contracts
import modules.auth.mfa_backup_codes.audit_actions as mfa_backup_codes_audit_actions
import modules.auth.mfa_backup_codes.crud as mfa_backup_codes_crud
import modules.auth.mfa_backup_codes.event_publishers as mfa_backup_codes_event_publishers

# Backup-code alphabet: uppercase ASCII + digits with visually ambiguous
# characters removed (0, O, 1, I) to reduce user transcription errors.
_BACKUP_CODE_ALPHABET = "23456789ABCDEFGHJKLMNPQRSTUVWXYZ"
_BACKUP_CODE_LENGTH = 8


def generate_backup_code() -> str:
    """Generate a cryptographically secure 8-character backup code.

    Format: ``XXXX-XXXX`` (uppercase alphanumeric, no ambiguous chars).
    Excludes ``0``, ``O``, ``1``, ``I`` to prevent transcription confusion.
    Provides ~40 bits of entropy per code (8 chars from a 32-char alphabet).

    Returns:
        Formatted backup code, e.g. ``"A3K9-7BDF"``.
    """
    code = "".join(secrets.choice(_BACKUP_CODE_ALPHABET) for _ in range(_BACKUP_CODE_LENGTH))
    return f"{code[:4]}-{code[4:]}"


def create_backup_codes(
    user_id: int, password_hasher: credentials_contracts.SupportsHashPassword, db: Session
) -> list[str]:
    """Generate and stage replacement backup codes for a user."""
    codes = [generate_backup_code() for _ in range(10)]
    code_hashes = [password_hasher.hash_password(code) for code in codes]
    mfa_backup_codes_crud.create_backup_codes(user_id, code_hashes, db)
    return codes


def verify_and_consume_backup_code(
    user_id: int,
    code: str,
    password_verifier: credentials_contracts.SupportsVerifyPassword,
    db: Session,
) -> bool:
    """Verify and consume a backup code for MFA authentication.

    Verifies the supplied code against every one of the user's unused backup
    code hashes and, on a match, marks that code as consumed via
    ``mark_backup_code_as_used``, and stages the use in the audit trail and as an event that tells the owner, both
    with the number of codes left.

    The loop deliberately does **not** short-circuit on the first match: it
    runs a verification for every stored hash so that the number of (slow,
    constant-time) Argon2 verifications — and therefore the wall-clock
    latency — does not depend on the matching code's position in the list.
    This removes a timing side channel that could otherwise hint at how many
    backup codes remain or where a valid code sits. Step-up/MFA progressive
    lockout remains the primary guard against guessing.

    Args:
        user_id: User ID to verify the backup code for.
        code: Plaintext backup code submitted by the user (``XXXX-XXXX``).
        password_verifier: Object implementing SupportsVerifyPassword, used to verify the code against stored hashes.
        db: Database session.

    Returns:
        ``True`` if the code matched an unused backup code and was consumed,
        ``False`` otherwise. The caller commits the consumption together with its audit row.
    """
    # Get all unused codes for this user
    unused_codes = mfa_backup_codes_crud.get_user_unused_backup_codes(user_id, db)

    # Verify against every stored hash without short-circuiting so the
    # number of Argon2 verifications is independent of match position
    # (constant-time-equivalent across the candidate set).
    matched_code_id: int | None = None
    for unused_code in unused_codes:
        if password_verifier.verify_password(code, unused_code.code_hash) and matched_code_id is None:
            matched_code_id = unused_code.id

    if matched_code_id is not None:
        # Valid code found - mark as used (by primary key). A concurrent request may have consumed it first.
        try:
            mfa_backup_codes_crud.mark_backup_code_as_used(matched_code_id, user_id, db)
        except core_exceptions.NotFoundError:
            return False
        jasil_audit.stage(
            db,
            mfa_backup_codes_audit_actions.BACKUP_CODE_USE,
            target_type="user",
            target_id=str(user_id),
            target_owner_id=str(user_id),
            details=mfa_backup_codes_audit_actions.BackupCodeUseDetails(remaining_codes=len(unused_codes) - 1),
        )
        mfa_backup_codes_event_publishers.publish_backup_code_used(user_id, len(unused_codes) - 1, db)
        return True

    # No matching code found
    return False
