"""ORM↔schema transformation for users.

``crud`` calls these at its edges so ORM rows never leave the persistence layer.
"""

import modules.users.users.models as users_models
import modules.users.users.schema as users_schema
import modules.users.users.signing as users_signing


def to_read_schema(user: users_models.Users) -> users_schema.UsersRead:
    """Convert one ORM user to its read schema, resolving the photo URL.

    ``photo_path`` holds a ``StorageProvider`` key, not a servable path, so this
    is where it becomes an addressable (signed, token-gated) URL.

    Args:
        user: The user ORM instance.

    Returns:
        The user as a read schema.
    """
    schema = users_schema.UsersRead.model_validate(user)
    schema.photo_path = users_signing.user_image_url(user.photo_path, user.id)
    return schema
