"""Migration tracking persistence on the real database."""

import pytest

import core.exceptions as core_exceptions
import migrations.crud as migrations_crud
import migrations.models as migrations_models
from tests._factories.migrations import make_migration


def test_marking_executed_stages_the_change_for_the_callers_transaction(db):
    make_migration(db, 4)

    result = migrations_crud.set_migration_as_executed(4, db)

    assert result.id == 4
    assert result.executed is True
    db.expire_all()
    assert db.get(migrations_models.Migration, 4).executed is True


def test_marking_a_missing_migration_raises_not_found(db):
    with pytest.raises(core_exceptions.NotFoundError, match="Migration not found"):
        migrations_crud.set_migration_as_executed(4, db)


def test_only_the_migrations_not_yet_executed_are_pending(db):
    make_migration(db, 1, executed=True)
    pending = make_migration(db, 2)

    # The v0.22 reprocess (id 15) is pending in a freshly migrated database.
    assert {row.id for row in migrations_crud.get_migrations_not_executed(db)} == {15, pending.id}
