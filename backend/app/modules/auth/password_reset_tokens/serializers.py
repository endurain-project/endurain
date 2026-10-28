"""Convert password reset token ORM rows into internal contracts."""

import modules.auth.password_reset_tokens.contracts as password_reset_contracts
import modules.auth.password_reset_tokens.models as password_reset_models


def to_state(row: password_reset_models.PasswordResetToken) -> password_reset_contracts.PasswordResetTokenState:
    """Return the internal state contract for a token row."""
    return password_reset_contracts.PasswordResetTokenState.model_validate(row)
