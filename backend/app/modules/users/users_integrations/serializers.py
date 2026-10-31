"""ORM↔schema transformation for user integrations.

``crud`` calls these at its edges so ORM rows never leave the persistence layer.
"""

import modules.users.users_integrations.models as user_integrations_models
import modules.users.users_integrations.schema as user_integrations_schema


def to_read_schema(
    integrations: user_integrations_models.UsersIntegrations,
) -> user_integrations_schema.UsersIntegrationsRead:
    """Transform a user integrations ORM row into its read schema.

    Args:
        integrations: The user integrations ORM instance.

    Returns:
        The user integrations as a schema.
    """
    return user_integrations_schema.UsersIntegrationsRead.model_validate(integrations)
