"""User privacy settings utility functions."""

import users.users_privacy_settings.schema as users_privacy_settings_schema


def visibility_to_int(
    visibility: str | users_privacy_settings_schema.ActivityVisibility | None,
) -> int:
    """
    Convert visibility string or enum to integer.

    Args:
        visibility: Visibility as string, enum, or None.

    Returns:
        Integer representation (0=public, 1=followers, 2=private).
    """
    if visibility is None:
        return 0
    value = (
        visibility.value
        if isinstance(visibility, users_privacy_settings_schema.ActivityVisibility)
        else visibility
    )
    mapping = {
        "public": 0,
        "followers": 1,
        "private": 2,
    }
    return mapping.get(value, 0)
