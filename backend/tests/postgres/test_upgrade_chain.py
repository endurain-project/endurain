"""The real Alembic chain, run against an empty database and against a seeded v0.20.x install."""

import pytest
import sqlalchemy as sa

from tests._helpers import alembic_chain

_REVISION_0 = "c5cfe02a11c2"
_REVISION_84 = "b84e9f3a6c25"
_REVISION_85 = "b41c0afdc9d9"
_REVISION_86 = "3e7a91d4c0b8"
_RETIRED_DATA_MIGRATIONS = {1, 2, 3, 4, 5, 6, 8, 9, 10}
_UNPREFIXED_SUBSTRATE_TABLES = ("event_log", "event_outbox", "processing_jobs")


def _scalar(engine, statement: str):
    with engine.connect() as connection:
        return connection.execute(sa.text(statement)).scalar()


def _migrations_state(engine) -> dict[int, bool]:
    with engine.connect() as connection:
        return {row.id: row.executed for row in connection.execute(sa.text("SELECT id, executed FROM migrations"))}


def _substrate_row_counts(engine) -> dict[str, int]:
    with engine.connect() as connection:
        return {
            name: connection.execute(sa.select(sa.func.count()).select_from(sa.table(name))).scalar_one()
            for name in _UNPREFIXED_SUBSTRATE_TABLES
        }


def _assert_every_table_has_rows(engine) -> None:
    counts = {**alembic_chain.row_counts(engine), **_substrate_row_counts(engine)}
    assert [name for name, count in counts.items() if count == 0] == []


def _seed(engine, seeder) -> None:
    with engine.begin() as connection:
        seeder(connection)


def test_a_fresh_install_upgrades_to_head_and_matches_the_models(upgrade_db):
    alembic_chain.upgrade(upgrade_db, "head")

    assert alembic_chain.schema_differences(upgrade_db) == []
    alembic_chain.bootstrap_substrate(upgrade_db)
    assert alembic_chain.schema_differences(upgrade_db) == []
    assert _migrations_state(upgrade_db) == {7: True, 11: False, 12: False}
    assert _scalar(upgrade_db, "SELECT to_regclass('cadence_spm_migration_rows')") is None


def test_a_seeded_v0_20_install_upgrades_to_head_keeping_every_row(upgrade_db):
    alembic_chain.upgrade(upgrade_db, alembic_chain.V0_20_HEAD)
    _seed(upgrade_db, alembic_chain.seed_v0_20)
    assert len(alembic_chain.row_counts(upgrade_db)) + len(_UNPREFIXED_SUBSTRATE_TABLES) == 41
    _assert_every_table_has_rows(upgrade_db)
    alembic_chain.upgrade(upgrade_db, _REVISION_84)
    _seed(upgrade_db, alembic_chain.seed_v0_21)
    before = alembic_chain.row_counts(upgrade_db)
    assert before.pop("cadence_spm_migration_rows") == 0

    alembic_chain.upgrade(upgrade_db, "head")

    after = alembic_chain.row_counts(upgrade_db)
    assert after == {**before, "migrations": before["migrations"] - 9}
    assert set(_migrations_state(upgrade_db)) == {7, 11, 12}
    assert _scalar(upgrade_db, "SELECT to_regclass('cadence_spm_migration_rows')") is None
    assert _scalar(upgrade_db, "SELECT start_time FROM activity_sets WHERE id = 1").isoformat() == (
        "2024-05-01T10:00:00+00:00"
    )
    assert alembic_chain.schema_differences(upgrade_db) == []
    alembic_chain.bootstrap_substrate(upgrade_db)
    assert alembic_chain.schema_differences(upgrade_db) == []


def test_a_seeded_install_at_head_has_a_row_in_every_table(upgrade_db):
    alembic_chain.upgrade(upgrade_db, alembic_chain.V0_20_HEAD)
    _seed(upgrade_db, alembic_chain.seed_v0_20)
    alembic_chain.upgrade(upgrade_db, _REVISION_84)
    _seed(upgrade_db, alembic_chain.seed_v0_21)
    alembic_chain.upgrade(upgrade_db, "head")

    _assert_every_table_has_rows(upgrade_db)


def test_the_upgrade_refuses_while_a_v0_20_data_migration_is_pending(upgrade_db):
    alembic_chain.upgrade(upgrade_db, alembic_chain.V0_20_HEAD)
    _seed(upgrade_db, alembic_chain.seed_v0_20)
    with upgrade_db.begin() as connection:
        connection.execute(sa.text("UPDATE migrations SET executed = false WHERE id = 3"))
        connection.execute(sa.text("DELETE FROM migrations WHERE id = 9"))
    before = _migrations_state(upgrade_db)

    with pytest.raises(RuntimeError, match=r"Data migrations 3, 9 "):
        alembic_chain.upgrade(upgrade_db, "head")

    assert _scalar(upgrade_db, "SELECT version_num FROM alembic_version") == alembic_chain.V0_20_HEAD
    assert _migrations_state(upgrade_db) == before


def test_revision_86_is_reversible(upgrade_db):
    alembic_chain.upgrade(upgrade_db, "head")

    alembic_chain.downgrade(upgrade_db, _REVISION_85)
    differences = [
        entry
        for difference in alembic_chain.schema_differences(upgrade_db)
        for entry in (difference if isinstance(difference, list) else [difference])
    ]
    kinds = sorted(entry[0] for entry in differences)
    assert kinds == ["modify_comment"] * 4 + ["modify_type"]

    alembic_chain.upgrade(upgrade_db, "head")
    assert alembic_chain.schema_differences(upgrade_db) == []


def test_revision_85_is_irreversible(upgrade_db):
    alembic_chain.upgrade(upgrade_db, "head")
    alembic_chain.downgrade(upgrade_db, _REVISION_85)

    with pytest.raises(NotImplementedError):
        alembic_chain.downgrade(upgrade_db, _REVISION_84)

    assert _scalar(upgrade_db, "SELECT version_num FROM alembic_version") == _REVISION_85
