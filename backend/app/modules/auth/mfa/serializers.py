"""MFA ORM serializers."""

import modules.auth.mfa.contracts as mfa_contracts
import modules.auth.mfa.models as mfa_models


def to_state_read(row: mfa_models.UsersMFA) -> mfa_contracts.MFAStateRead:
    """Convert a users-MFA row to its internal read shape."""
    return mfa_contracts.MFAStateRead.model_validate(row)
