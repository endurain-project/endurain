"""CRUD operations for server settings."""

from sqlalchemy import select
from sqlalchemy.orm import Session

import core.exceptions as core_exceptions
import modules.server_settings.models as server_settings_models
import modules.server_settings.schema as server_settings_schema

_SINGLETON_ID = 1


def _find_server_settings_model(
    db: Session, *, for_update: bool = False
) -> server_settings_models.ServerSettings | None:
    """Load the singleton server settings row.

    Args:
        db: Database session.
        for_update: Lock the row until the transaction ends, so concurrent writers
            (other workers or replicas included) queue instead of overwriting each other.

    Returns:
        The mapped ServerSettings ORM instance, or None if the row does not exist.
    """
    stmt = select(server_settings_models.ServerSettings).where(
        server_settings_models.ServerSettings.id == _SINGLETON_ID
    )
    if for_update:
        # A locked read must see what the previous holder committed, not a stale loaded copy.
        stmt = stmt.with_for_update().execution_options(populate_existing=True)
    return db.execute(stmt).scalar_one_or_none()


def _lock_server_settings_model(db: Session) -> server_settings_models.ServerSettings:
    """Load the singleton server settings row for writing, locked, or fail.

    Args:
        db: Database session.

    Returns:
        The mapped ServerSettings ORM instance.

    Raises:
        ServiceUnavailableError: If the settings row does not exist.
    """
    db_server_settings = _find_server_settings_model(db, for_update=True)
    if db_server_settings is None:
        raise core_exceptions.ServiceUnavailableError("Server settings are not initialised.")
    return db_server_settings


def get_server_settings(db: Session, *, for_update: bool = False) -> server_settings_schema.ServerSettingsRead | None:
    """Retrieve the singleton server settings.

    Args:
        db: Database session.
        for_update: Lock the row until the transaction ends; for a read that decides a write.

    Returns:
        The settings as stored (the tile API key stays encrypted), or None if not found.
    """
    db_server_settings = _find_server_settings_model(db, for_update=for_update)
    if db_server_settings is None:
        return None
    return server_settings_schema.ServerSettingsRead.model_validate(db_server_settings)


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
    db_server_settings = _lock_server_settings_model(db)

    for key, value in server_settings.model_dump(exclude_unset=True).items():
        setattr(db_server_settings, key, value)

    db.flush()
    db.refresh(db_server_settings)

    return server_settings_schema.ServerSettingsRead.model_validate(db_server_settings)


def set_login_photo(is_set: bool, db: Session) -> None:
    """Stage whether a custom login photo is configured.

    Args:
        is_set: True when a login photo exists.
        db: Database session.

    Raises:
        ServiceUnavailableError: If the settings row does not exist.
    """
    db_server_settings = _lock_server_settings_model(db)
    db_server_settings.login_photo_set = is_set
    db.flush()
