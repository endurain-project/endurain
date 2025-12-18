import secrets
import string

from datetime import datetime, timezone

import auth.mfa_backup_codes.crud as mfa_backup_codes_crud

import auth.password_hasher as auth_password_hasher

from sqlalchemy.orm import Session


def generate_backup_code() -> str:
    """
    Generate a cryptographically secure 8-character backup code.

    Format: XXXX-XXXX (uppercase alphanumeric, no ambiguous chars)
    Excludes: 0, O, 1, I, l (to prevent confusion)
    Entropy: ~40 bits per code (8 chars from 32-char alphabet)

    Returns:
        str: Formatted backup code (e.g., "A3K9-7BDF")
    """
    alphabet = string.ascii_uppercase + string.digits
    # Remove ambiguous characters
    alphabet = (
        alphabet.replace("0", "").replace("O", "").replace("1", "").replace("I", "")
    )

    # Generate 8 random characters
    code = "".join(secrets.choice(alphabet) for _ in range(8))

    # Format as XXXX-XXXX
    return f"{code[:4]}-{code[4:]}"


def verify_and_consume_backup_code(
    user_id: int,
    code: str,
    password_hasher: auth_password_hasher.PasswordHasher,
    db: Session,
) -> bool:
    # Get all unused codes for this user
    unused_codes = mfa_backup_codes_crud.get_user_unused_backup_codes(user_id, db)

    # Try each unused code (constant-time for each)
    for unused_code in unused_codes:
        if password_hasher.verify(code, unused_code.code_hash):
            # Valid code found - mark as used
            mfa_backup_codes_crud.mark_backup_code_as_used(
                unused_code.code_hash, user_id, db
            )

            # Return success
            return True

    # No matching code found
    return False
