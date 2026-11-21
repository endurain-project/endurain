"""Data migration tracking rows as the application stores them, for tests on the real database."""

from sqlalchemy.orm import Session

import migrations.models as migrations_models
import migrations.schema as migrations_schema


def make_migration(
    db: Session, migration_id: int, *, executed: bool = False, name: str | None = None
) -> migrations_schema.MigrationRead:
    """Stage a data migration's tracking row (flushed, not committed).

    Args:
        db: Database session.
        migration_id: The migration's identifier, which the startup runner looks its handler up by.
        executed: Whether the migration already ran.
        name: The migration's name; ``m<id>`` when omitted.

    Returns:
        The staged row.
    """
    row = migrations_models.Migration(
        id=migration_id, name=name or f"m{migration_id}", description="a test migration", executed=executed
    )
    db.add(row)
    db.flush()
    return migrations_schema.MigrationRead.model_validate(row)
