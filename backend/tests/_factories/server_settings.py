"""The singleton settings rows the migrations seed, edited as the application stores them.

The migrated schema holds one ``server_settings`` row and one ``mail_settings`` row (id 1); a test edits those and
never inserts a second one.
"""

from sqlalchemy.orm import Session

import modules.server_settings.change_utils as server_settings_change_utils
import modules.server_settings.crud as server_settings_crud
import modules.server_settings.schema as server_settings_schema

_SERVER_SETTINGS_OWNED = {"id", "version", "login_photo_set"}
_MAIL_SETTINGS_OWNED = {"id", "version"}


def _encrypt(plain: object) -> str | None:
    """Encrypt a plain-text secret for storage; None or empty stays unset."""
    assert plain is None or isinstance(plain, str)
    return server_settings_change_utils.encrypt_secret(plain)


def edit_server_settings(db: Session, **fields: object) -> server_settings_schema.ServerSettingsRead:
    """Stage new values on the seeded server settings through the module's own edit function (flushed, not committed).

    Args:
        db: Database session.
        **fields: Setting values to change; an API key is given in plain text and stored encrypted.

    Returns:
        The settings as stored after the edit.
    """
    current = server_settings_crud.get_server_settings(db)
    assert current is not None
    values = current.model_dump(exclude=_SERVER_SETTINGS_OWNED) | fields
    for key_field in ("tileserver_api_key", "geocoding_api_key"):
        if key_field in fields:
            values[key_field] = _encrypt(fields[key_field])
    return server_settings_crud.edit_server_settings(server_settings_schema.ServerSettingsEdit(**values), db)


def edit_mail_settings(db: Session, **fields: object) -> server_settings_schema.MailSettingsRead:
    """Stage new values on the seeded mail settings through the module's own edit function (flushed, not committed).

    Args:
        db: Database session.
        **fields: Mail setting values to change; the password is given in plain text and stored encrypted.

    Returns:
        The mail settings as stored after the edit.
    """
    current = server_settings_crud.get_mail_settings(db)
    assert current is not None
    values = current.model_dump(exclude=_MAIL_SETTINGS_OWNED) | fields
    if "password" in fields:
        values["password"] = _encrypt(fields["password"])
    return server_settings_crud.edit_mail_settings(server_settings_schema.MailSettingsEdit(**values), db)
