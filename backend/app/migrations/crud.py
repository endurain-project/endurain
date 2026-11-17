"""CRUD operations for migration tracking."""

import uuid
from typing import overload

from sqlalchemy import Integer, Uuid, column, select, table, text
from sqlalchemy.orm import Session

import core.exceptions as core_exceptions
import migrations.models as migrations_models
import migrations.schema as migrations_schema

#: Scratch table of the UUID conversion revisions: the old and new id of every converted row, until migration 13
#: has renamed the stored files and drops it.
_UUID_MIGRATION_IDS = table(
    "uuid_migration_ids", column("table_name"), column("old_id", Integer), column("new_id", Uuid)
)

# Private internal helpers


@overload
def _transform_migrations(
    migrations: migrations_models.Migration,
) -> migrations_schema.MigrationRead: ...


@overload
def _transform_migrations(
    migrations: list[migrations_models.Migration],
) -> list[migrations_schema.MigrationRead]: ...


def _transform_migrations(
    migrations: migrations_models.Migration | list[migrations_models.Migration],
) -> migrations_schema.MigrationRead | list[migrations_schema.MigrationRead]:
    """
    Transform a migration or list of migrations to a Pydantic schema.

      Args:
        migrations: The migration ORM instance or list of instances.

      Returns:
        The migration(s) as a schema.
    """
    if isinstance(migrations, list):
        return [migrations_schema.MigrationRead.model_validate(m) for m in migrations]
    return migrations_schema.MigrationRead.model_validate(migrations)


def _get_migration_by_id(migration_id: int, db: Session) -> migrations_models.Migration:
    """
    Retrieve a migration by its ID from the database.

    Args:
        migration_id: ID of the migration to retrieve.
        db: Database session.

    Returns:
        Migration ORM instance.

    Raises:
        NotFoundError: If the migration does not exist.
    """
    stmt = select(migrations_models.Migration).where(migrations_models.Migration.id == migration_id)
    db_migration = db.execute(stmt).scalar_one_or_none()

    if db_migration is None:
        raise core_exceptions.NotFoundError("Migration not found")

    return db_migration


# Public CRUD functions


def get_migrations_not_executed(
    db: Session,
) -> list[migrations_schema.MigrationRead]:
    """
    Retrieve all unexecuted migrations.

    Args:
        db: Database session.

    Returns:
        List of unexecuted Migration schemas.

    Raises:
    """
    stmt = select(migrations_models.Migration).where(migrations_models.Migration.executed.is_(False))
    db_migrations = db.execute(stmt).scalars().all()
    return _transform_migrations(list(db_migrations))


def set_migration_as_executed(
    migration_id: int,
    db: Session,
) -> migrations_schema.MigrationRead:
    """
    Mark a migration as executed by its ID.

    Args:
        migration_id: ID of the migration to mark as executed.
        db: Database session.

    Returns:
        The updated Migration schema.

    Raises:
        NotFoundError: If the migration does not exist.
    """
    db_migration = _get_migration_by_id(migration_id, db)

    db_migration.executed = True
    db.flush()
    db.refresh(db_migration)
    return _transform_migrations(db_migration)


def get_uuid_migration_ids(table_name: str, db: Session) -> dict[int, uuid.UUID]:
    """
    Retrieve the old and new ids a conversion revision recorded for one table.

    Args:
        table_name: The converted table.
        db: Database session.

    Returns:
        The new UUID of each old integer id.
    """
    stmt = select(_UUID_MIGRATION_IDS.c.old_id, _UUID_MIGRATION_IDS.c.new_id).where(
        _UUID_MIGRATION_IDS.c.table_name == table_name
    )
    return {old_id: new_id for old_id, new_id in db.execute(stmt).all()}


def drop_uuid_migration_ids(db: Session) -> None:
    """
    Drop the table of recorded ids. The caller commits.

    Args:
        db: Database session.
    """
    db.execute(text("DROP TABLE uuid_migration_ids"))
