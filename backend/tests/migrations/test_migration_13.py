"""Tests for migration 13: stored files named by an integer id are renamed to their UUID."""

import uuid
from pathlib import Path
from unittest.mock import patch

import pytest
import sqlalchemy as sa
from jasil.backends.storage_local import LocalStorage
from sqlalchemy.orm import Session

import migrations.migration_13 as migration_13
import migrations.models as migrations_models
import migrations.utils as migrations_utils

_MODULE = "migrations.migration_13"
_AREA = "identity_provider_icons"
_FIRST = uuid.UUID("11111111-1111-4111-8111-111111111111")
_SECOND = uuid.UUID("22222222-2222-4222-8222-222222222222")
_IDS = sa.Table(
    "uuid_migration_ids",
    sa.MetaData(),
    sa.Column("table_name", sa.String(64), primary_key=True),
    sa.Column("old_id", sa.Integer, primary_key=True),
    sa.Column("new_id", sa.Uuid, nullable=False),
)


class _FailingCopy(LocalStorage):
    """A storage that cannot copy the object stored under the key ``fail``."""

    fail = ""

    def copy(self, src_area: str, src_key: str, dst_area: str, dst_key: str) -> None:
        if src_key == self.fail:
            raise OSError("disk full")
        super().copy(src_area, src_key, dst_area, dst_key)


@pytest.fixture
def db():
    engine = sa.create_engine("sqlite://", poolclass=sa.StaticPool)
    migrations_models.Migration.__table__.create(engine)
    _IDS.create(engine)
    with Session(engine) as session:
        session.add(migrations_models.Migration(id=13, name="v0.21.0", description="rename", executed=False))
        session.execute(
            sa.insert(_IDS),
            [
                {"table_name": "identity_providers", "old_id": 1, "new_id": _FIRST},
                {"table_name": "identity_providers", "old_id": 2, "new_id": _SECOND},
            ],
        )
        session.commit()
        yield session


def _run(storage: LocalStorage, db: Session) -> None:
    with patch(f"{_MODULE}.platform_runtime") as runtime:
        runtime.get_active_platform.return_value.storage = storage
        migration_13.process_migration_13(db)


def _executed(db: Session) -> bool:
    return db.execute(
        sa.select(migrations_models.Migration.executed).where(migrations_models.Migration.id == 13)
    ).scalar_one()


def _table_exists(db: Session) -> bool:
    return sa.inspect(db.connection()).has_table("uuid_migration_ids")


class TestProcessMigration13:
    def test_is_registered_as_a_synchronous_data_migration(self):
        assert migrations_utils._SYNC_MIGRATIONS[13] is migration_13.process_migration_13

    def test_renames_the_icons_deletes_the_orphans_and_skips_uuid_keys(self, tmp_path: Path, db: Session):
        storage = LocalStorage(str(tmp_path))
        storage.save(_AREA, "1", b"first", "image/png")
        storage.save(_AREA, "2", b"second", "image/png")
        storage.save(_AREA, "99", b"orphan", "image/png")
        uuid_key = str(uuid.UUID("33333333-3333-4333-8333-333333333333"))
        storage.save(_AREA, uuid_key, b"kept", "image/png")

        _run(storage, db)

        assert sorted(storage.list_keys(_AREA, "")) == sorted([str(_FIRST), str(_SECOND), uuid_key])
        assert storage.get(_AREA, str(_FIRST)) == b"first"
        assert storage.get(_AREA, str(_SECOND)) == b"second"
        assert storage.get(_AREA, uuid_key) == b"kept"
        assert _executed(db) is True
        assert _table_exists(db) is False

    def test_an_existing_uuid_key_is_not_overwritten(self, tmp_path: Path, db: Session):
        storage = LocalStorage(str(tmp_path))
        storage.save(_AREA, "1", b"old", "image/png")
        storage.save(_AREA, str(_FIRST), b"already copied", "image/png")

        _run(storage, db)

        assert storage.list_keys(_AREA, "") == [str(_FIRST)]
        assert storage.get(_AREA, str(_FIRST)) == b"already copied"

    def test_a_second_run_changes_nothing(self, tmp_path: Path, db: Session):
        storage = LocalStorage(str(tmp_path))
        storage.save(_AREA, "1", b"first", "image/png")
        _run(storage, db)

        _run(storage, db)

        assert storage.list_keys(_AREA, "") == [str(_FIRST)]
        assert storage.get(_AREA, str(_FIRST)) == b"first"
        assert _executed(db) is True

    def test_a_failure_keeps_the_table_and_the_migration_pending_and_the_next_run_finishes(
        self, tmp_path: Path, db: Session, caplog: pytest.LogCaptureFixture
    ):
        storage = _FailingCopy(str(tmp_path))
        storage.fail = "1"
        storage.save(_AREA, "1", b"first", "image/png")
        storage.save(_AREA, "2", b"second", "image/png")

        _run(storage, db)

        assert sorted(storage.list_keys(_AREA, "")) == sorted(["1", str(_SECOND)])
        assert _executed(db) is False
        assert _table_exists(db) is True
        assert any(
            record.levelname == "ERROR" and "identity_provider_icons/1" in record.getMessage()
            for record in caplog.records
        )
        assert "first" not in caplog.text

        storage.fail = ""
        _run(storage, db)

        assert sorted(storage.list_keys(_AREA, "")) == sorted([str(_FIRST), str(_SECOND)])
        assert _executed(db) is True
        assert _table_exists(db) is False

    def test_a_missing_table_is_an_error_and_leaves_the_migration_pending(
        self, tmp_path: Path, db: Session, caplog: pytest.LogCaptureFixture
    ):
        db.execute(sa.text("DROP TABLE uuid_migration_ids"))
        db.commit()

        _run(LocalStorage(str(tmp_path)), db)

        assert _executed(db) is False
        assert any(record.levelname == "ERROR" for record in caplog.records)
