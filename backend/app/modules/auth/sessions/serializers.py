"""Session row serialization."""

import modules.auth.sessions.contracts as sessions_contracts
import modules.auth.sessions.models as sessions_models


def to_read_schema(row: sessions_models.UsersSessions) -> sessions_contracts.SessionRead:
    """Convert a session row to its internal DTO."""
    return sessions_contracts.SessionRead.model_validate(row)
