"""ORM↔schema transformation for server settings.

``crud`` calls these at its edges so ORM rows never leave the persistence layer.
"""

import modules.server_settings.models as server_settings_models
import modules.server_settings.schema as server_settings_schema


def to_server_settings_read(
    row: server_settings_models.ServerSettings,
) -> server_settings_schema.ServerSettingsRead:
    """Convert the server settings row to its Read schema.

    Args:
        row: The ORM row to convert.

    Returns:
        The settings as stored (the API keys stay encrypted).
    """
    return server_settings_schema.ServerSettingsRead.model_validate(row)


def to_mail_settings_read(row: server_settings_models.MailSettings) -> server_settings_schema.MailSettingsRead:
    """Convert the mail settings row to its Read schema.

    Args:
        row: The ORM row to convert.

    Returns:
        The settings as stored (the password stays encrypted).
    """
    return server_settings_schema.MailSettingsRead.model_validate(row)
