"""IdP link-token DTO conversion."""

import modules.auth.identity_provider_link_tokens.models as idp_link_token_models
import modules.auth.identity_provider_link_tokens.schema as idp_link_token_schema


def to_read_schema(row: idp_link_token_models.IdpLinkToken) -> idp_link_token_schema.IdpLinkTokenRead:
    """Convert a persisted token row to its read schema."""
    return idp_link_token_schema.IdpLinkTokenRead.model_validate(row)
