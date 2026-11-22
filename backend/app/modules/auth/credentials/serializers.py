"""Credential row serialization."""

import modules.auth.credentials.contracts as credentials_contracts
import modules.auth.credentials.models as credentials_models


def to_read_schema(row: credentials_models.LocalCredential) -> credentials_contracts.CredentialRead:
    """Convert a local credential row to its internal DTO."""
    return credentials_contracts.CredentialRead.model_validate(row)
