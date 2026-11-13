"""Tests for migration 14: the state namespace is cleared exactly once."""

from unittest.mock import MagicMock, patch

import pytest
import sqlalchemy as sa
from sqlalchemy.orm import Session

import migrations.migration_14 as migration_14
import migrations.models as migrations_models
import migrations.utils as migrations_utils
from core.database import Base

_MODULE = "migrations.migration_14"


@pytest.fixture
def db():
    engine = sa.create_engine("sqlite://", poolclass=sa.StaticPool)
    Base.metadata.create_all(engine, tables=[migrations_models.Migration.__table__])
    with Session(engine) as session:
        session.add(migrations_models.Migration(id=14, name="v0.21.0", description="clear the state", executed=False))
        session.commit()
        yield session


def _executed(db: Session) -> bool:
    return db.execute(
        sa.select(migrations_models.Migration.executed).where(migrations_models.Migration.id == 14)
    ).scalar_one()


def _run(db: Session, state: MagicMock) -> None:
    with patch(f"{_MODULE}.platform_runtime") as runtime:
        runtime.get_active_platform.return_value.state = state
        migration_14.process_migration_14(db)


class TestProcessMigration14:
    def test_is_registered_as_a_synchronous_data_migration(self):
        assert migrations_utils._SYNC_MIGRATIONS[14] is migration_14.process_migration_14

    def test_clears_the_namespace_and_is_marked_executed(self, db: Session):
        state = MagicMock()

        _run(db, state)

        state.delete_prefix.assert_called_once_with("endurain:")
        assert _executed(db) is True

    def test_a_failed_clear_leaves_the_migration_pending_and_the_retry_clears_once(self, db: Session):
        state = MagicMock()
        state.delete_prefix.side_effect = [OSError("down"), None]

        _run(db, state)
        assert _executed(db) is False

        _run(db, state)
        assert _executed(db) is True
        assert state.delete_prefix.call_count == 2
