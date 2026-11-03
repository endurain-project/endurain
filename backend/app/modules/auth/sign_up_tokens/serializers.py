"""Convert sign-up token ORM rows into internal contracts."""

from sqlalchemy import Row

import modules.auth.sign_up_tokens.contracts as sign_up_contracts
import modules.auth.sign_up_tokens.models as sign_up_models


def to_state(row: sign_up_models.SignUpToken) -> sign_up_contracts.SignUpTokenState:
    """Return the internal state contract for a token row."""
    return sign_up_contracts.SignUpTokenState.model_validate(row)


def to_claim(row: Row[tuple[str, int, str | None, str | None]]) -> sign_up_contracts.SignUpTokenClaim:
    """Return the claim contract for the columns a token claim returned.

    A token that replaces an address is an email change, which must also name the address it confirms.
    """
    if row.previous_email is not None:
        return sign_up_contracts.EmailChangeClaim.model_validate(row, from_attributes=True)
    return sign_up_contracts.SignUpTokenClaim.model_validate(row, from_attributes=True)
