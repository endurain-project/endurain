"""Convert sign-up token ORM rows into internal contracts."""

import modules.auth.sign_up_tokens.contracts as sign_up_contracts
import modules.auth.sign_up_tokens.models as sign_up_models


def to_state(row: sign_up_models.SignUpToken) -> sign_up_contracts.SignUpTokenState:
    """Return the internal state contract for a token row."""
    return sign_up_contracts.SignUpTokenState.model_validate(row)
