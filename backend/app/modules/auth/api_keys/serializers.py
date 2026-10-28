"""API-key row serialization."""

import modules.auth.api_keys.models as api_keys_models
import modules.auth.api_keys.schema as api_keys_schema


def to_read_schema(row: api_keys_models.UsersApiKeys) -> api_keys_schema.UsersApiKeyRead:
    """Convert an API-key row to its safe read representation."""
    return api_keys_schema.UsersApiKeyRead.model_validate(row)
