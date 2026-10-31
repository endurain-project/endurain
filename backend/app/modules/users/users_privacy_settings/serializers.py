"""ORM↔schema transformation for user privacy settings.

``crud`` calls these at its edges so ORM rows never leave the persistence layer.
"""

import modules.users.users_privacy_settings.models as users_privacy_settings_models
import modules.users.users_privacy_settings.schema as users_privacy_settings_schema


def to_read_schema(
    privacy_settings: users_privacy_settings_models.UsersPrivacySettings,
) -> users_privacy_settings_schema.UsersPrivacySettingsRead:
    """Transform a privacy settings ORM row into its read schema.

    Args:
        privacy_settings: The user privacy settings ORM instance.

    Returns:
        The user privacy settings as a schema.
    """
    return users_privacy_settings_schema.UsersPrivacySettingsRead.model_validate(privacy_settings)
