"""OAuth-state row serialization."""

import modules.auth.oauth_state.models as oauth_state_models
import modules.auth.oauth_state.schema as oauth_state_schema


def to_read_schema(row: oauth_state_models.OAuthState) -> oauth_state_schema.OAuthStateRead:
    """Convert an OAuth-state row to its internal read model."""
    return oauth_state_schema.OAuthStateRead.model_validate(row)
