"""Application-level migration write orchestration."""

from sqlalchemy.orm import Session

import migrations.crud as migrations_crud
import migrations.schema as migrations_schema


def mark_executed(migration_id: int, db: Session) -> migrations_schema.MigrationRead:
    """Mark a migration as executed and commit the tracking change.

    Args:
        migration_id: ID of the migration to mark as executed.
        db: Database session.

    Returns:
        The updated migration.

    Raises:
        NotFoundError: If the migration does not exist.
    """
    migration = migrations_crud.set_migration_as_executed(migration_id, db)
    db.commit()
    return migration
