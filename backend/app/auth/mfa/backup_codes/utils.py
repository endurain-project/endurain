"""Utility helpers for MFA backup codes."""

from __future__ import annotations

import secrets

from sqlalchemy.orm import Session

import auth.mfa.backup_codes.crud as mfa_backup_codes_crud
from auth._internal.password_hasher import SupportsVerifyPassword

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


def verify_and_consume_backup_code(
    user_id: int,
    code: str,
    password_verifier: SupportsVerifyPassword,
    db: Session,
) -> bool:
    """Verify and consume a backup code for MFA authentication.

    Verifies the supplied code against every one of the user's unused backup
    code hashes and, on a match, marks that code as consumed via
    ``mark_backup_code_as_used``.

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
        ``False`` otherwise.
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
        # Valid code found - mark as used (by primary key)
        mfa_backup_codes_crud.mark_backup_code_as_used(matched_code_id, user_id, db)
        return True

    # No matching code found
    return False
