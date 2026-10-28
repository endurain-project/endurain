"""Identity-provider read operations exposed to auth peers."""

from sqlalchemy.orm import Session

import modules.auth.identity_providers.crud as identity_providers_crud
import modules.auth.identity_providers.schema as identity_providers_schema


def get_identity_providers_by_ids(
    idp_ids: list[int],
    db: Session,
) -> list[identity_providers_schema.IdentityProvider]:
    """Return identity providers matching a batch of IDs."""
    rows = identity_providers_crud.get_identity_providers_by_ids(idp_ids, db)
    return [identity_providers_schema.IdentityProvider.model_validate(row) for row in rows]
