"""CRUD operations for server settings."""

from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import flag_modified

import core.exceptions as core_exceptions
import modules.server_settings.models as server_settings_models
import modules.server_settings.schema as server_settings_schema
import modules.server_settings.serializers as server_settings_serializers

_SINGLETON_ID = 1


def _find_singleton[RowT: server_settings_models.ServerSettings | server_settings_models.MailSettings](
    model: type[RowT], db: Session, *, for_update: bool = False
) -> RowT | None:
    """Load a singleton settings row.

    Args:
        model: The settings model to load.
        db: Database session.
        for_update: Lock the row until the transaction ends, so concurrent writers
            (other workers or replicas included) queue instead of overwriting each other.

    Returns:
        The mapped instance, or None if the row does not exist.
    """
    stmt = select(model).where(model.id == _SINGLETON_ID)
    if for_update:
        # A locked read must see what the previous holder committed, not a stale loaded copy.
        stmt = stmt.with_for_update().execution_options(populate_existing=True)
    return db.execute(stmt).scalar_one_or_none()


def _lock_singleton[RowT: server_settings_models.ServerSettings | server_settings_models.MailSettings](
    model: type[RowT], label: str, db: Session
) -> RowT:
    """Load a singleton settings row for writing, locked, or fail.

    Args:
        model: The settings model to load.
        label: What the row holds, named in the failure message.
        db: Database session.

    Returns:
        The mapped instance.

    Raises:
        ServiceUnavailableError: If the settings row does not exist.
    """
    row = _find_singleton(model, db, for_update=True)
    if row is None:
        raise core_exceptions.ServiceUnavailableError(f"{label} settings are not initialised.")
    return row


def _apply(
    row: server_settings_models.ServerSettings | server_settings_models.MailSettings, fields: BaseModel, db: Session
) -> None:
    """Write the fields that were set onto a locked row and flush.

    Args:
        row: The locked settings row.
        fields: The request body; only the fields that were set are written.
        db: Database session.
    """
    for key, value in fields.model_dump(exclude_unset=True).items():
        setattr(row, key, value)
    db.flush()
    db.refresh(row)


def get_server_settings(db: Session, *, for_update: bool = False) -> server_settings_schema.ServerSettingsRead | None:
    """Retrieve the singleton server settings.

    Args:
        db: Database session.
        for_update: Lock the row until the transaction ends; for a read that decides a write.

    Returns:
        The settings as stored (the tile API key stays encrypted), or None if not found.
    """
    row = _find_singleton(server_settings_models.ServerSettings, db, for_update=for_update)
    if row is None:
        return None
    return server_settings_serializers.to_server_settings_read(row)


def edit_server_settings(
    server_settings: server_settings_schema.ServerSettingsEdit,
    db: Session,
) -> server_settings_schema.ServerSettingsRead:
    """Stage an update of the server settings.

    Args:
        server_settings: The fields to apply; only the ones that were set are written.
            A tile API key must already be encrypted.
        db: Database session.

    Returns:
        The updated settings as stored.

    Raises:
        ServiceUnavailableError: If the settings row does not exist.
    """
    row = _lock_singleton(server_settings_models.ServerSettings, "Server", db)
    _apply(row, server_settings, db)
    return server_settings_serializers.to_server_settings_read(row)


def set_login_photo(is_set: bool, db: Session) -> None:
    """Stage whether a custom login photo is configured.

    Args:
        is_set: True when a login photo exists.
        db: Database session.

    Raises:
        ServiceUnavailableError: If the settings row does not exist.
    """
    row = _lock_singleton(server_settings_models.ServerSettings, "Server", db)
    row.login_photo_set = is_set
    # A new photo leaves the flag as it was; flagging it forces the UPDATE that bumps the version,
    # which is the photo's entity tag.
    flag_modified(row, "login_photo_set")
    db.flush()


def get_mail_settings(db: Session, *, for_update: bool = False) -> server_settings_schema.MailSettingsRead | None:
    """Retrieve the singleton mail settings.

    Args:
        db: Database session.
        for_update: Lock the row until the transaction ends; for a read that decides a write.

    Returns:
        The settings as stored (the password stays encrypted), or None if not found.
    """
    row = _find_singleton(server_settings_models.MailSettings, db, for_update=for_update)
    if row is None:
        return None
    return server_settings_serializers.to_mail_settings_read(row)


def edit_mail_settings(
    mail_settings: server_settings_schema.MailSettingsEdit,
    db: Session,
) -> server_settings_schema.MailSettingsRead:
    """Stage an update of the mail settings.

    Args:
        mail_settings: The fields to apply; only the ones that were set are written.
            A password must already be encrypted.
        db: Database session.

    Returns:
        The updated settings as stored.

    Raises:
        ServiceUnavailableError: If the settings row does not exist.
    """
    row = _lock_singleton(server_settings_models.MailSettings, "Mail", db)
    _apply(row, mail_settings, db)
    return server_settings_serializers.to_mail_settings_read(row)
