"""ORM↔schema transformation for user default gear.

``crud`` calls these at its edges so ORM rows never leave the persistence layer.
"""

import modules.users.users_default_gear.models as users_default_gear_models
import modules.users.users_default_gear.schema as users_default_gear_schema


def to_read_schema(
    default_gear: users_default_gear_models.UsersDefaultGear,
) -> users_default_gear_schema.UsersDefaultGearRead:
    """Transform a user default gear ORM row into its read schema.

    Args:
        default_gear: The user default gear ORM instance.

    Returns:
        The user default gear as a schema.
    """
    return users_default_gear_schema.UsersDefaultGearRead.model_validate(default_gear)
