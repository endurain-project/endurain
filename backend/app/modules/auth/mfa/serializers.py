"""MFA ORM serializers."""

import modules.auth.mfa.contracts as mfa_contracts
import modules.auth.mfa.models as mfa_models


def to_read_schema(row: mfa_models.MFAFactor) -> mfa_contracts.MFAFactorRead:
    """Convert an MFA factor row to its internal read shape."""
    return mfa_contracts.MFAFactorRead.model_validate(row)
