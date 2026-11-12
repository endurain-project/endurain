"""The real Alembic chain, run against an empty database and against a seeded v0.20.x install."""

from collections import Counter
from datetime import timedelta

import pytest
import sqlalchemy as sa

from tests._helpers import alembic_chain

_REVISION_0 = "c5cfe02a11c2"
_REVISION_84 = "b84e9f3a6c25"
_REVISION_85 = "b41c0afdc9d9"
_REVISION_86 = "3e7a91d4c0b8"
_REVISION_87 = "e05703e64861"
_RETIRED_DATA_MIGRATIONS = {1, 2, 3, 4, 5, 6, 8, 9, 10}
_UNPREFIXED_SUBSTRATE_TABLES = ("event_log", "event_outbox", "processing_jobs")
#: The one table revision 87 empties by design: its record ids name health rows whose ids change.
_TABLE_EMPTIED_BY_REVISION_87 = "health_record_deletions"
_REVISION_87_TABLES = (
    "health_fasting",
    "health_poop",
    "health_sleep",
    "health_steps",
    "health_targets",
    "health_water",
    "health_weight",
    "health_record_deletions",
    "activity_deletions",
    "gear_deletions",
    "gear_component_deletions",
    "users_goals",
    "notifications",
    "followers",
    "follower_blocks",
    "follow_request_declines",
    "auth_known_devices",
    "mfa_factors",
    "mfa_backup_codes",
    "rotated_refresh_tokens",
    "users_integrations",
    "users_privacy_settings",
    "users_default_gear",
    "users_identity_providers",
    "idp_session_tokens",
)
_KEPT_TOMBSTONE_TABLES = ("activity_deletions", "gear_deletions", "gear_component_deletions")


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


def _assert_every_table_has_rows_but_the_emptied_one(engine) -> None:
    counts = {**alembic_chain.row_counts(engine), **_substrate_row_counts(engine)}
    assert counts.pop(_TABLE_EMPTIED_BY_REVISION_87) == 0
    assert [name for name, count in counts.items() if count == 0] == []


def _rows(engine, statement: str) -> list[tuple]:
    with engine.connect() as connection:
        return [tuple(row) for row in connection.execute(sa.text(statement))]


def _data_type(engine, table: str, column: str) -> str | None:
    with engine.connect() as connection:
        return connection.execute(
            sa.text(
                "SELECT data_type FROM information_schema.columns "
                "WHERE table_schema = 'public' AND table_name = :table AND column_name = :column"
            ),
            {"table": table, "column": column},
        ).scalar()


def _columns_of_type(engine, data_type: str, names: tuple[str, ...]) -> list[tuple[str, str]]:
    """Return the (table, column) pairs of the 25 revision 87 tables whose name is in ``names``, with that type."""
    with engine.connect() as connection:
        return [
            (row.table_name, row.column_name)
            for row in connection.execute(
                sa.text(
                    "SELECT table_name, column_name FROM information_schema.columns "
                    "WHERE table_schema = 'public' AND table_name = ANY(:tables) AND column_name = ANY(:names) "
                    "AND data_type = :data_type ORDER BY table_name, column_name"
                ),
                {"tables": list(_REVISION_87_TABLES), "names": list(names), "data_type": data_type},
            )
        ]


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
    assert after == {**before, "migrations": before["migrations"] - 9, _TABLE_EMPTIED_BY_REVISION_87: 0}
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

    _assert_every_table_has_rows_but_the_emptied_one(upgrade_db)


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


def _difference_kinds(engine) -> Counter:
    """Count the kinds of the differences between the database and the models."""
    return Counter(
        entry[0]
        for difference in alembic_chain.schema_differences(engine)
        for entry in (difference if isinstance(difference, list) else [difference])
    )


def test_revision_86_is_reversible(upgrade_db):
    # The models are at the head, so revision 87's changes show as differences at 86 as well.
    alembic_chain.upgrade(upgrade_db, _REVISION_86)
    at_86 = _difference_kinds(upgrade_db)

    alembic_chain.downgrade(upgrade_db, _REVISION_85)
    assert _difference_kinds(upgrade_db) - at_86 == Counter({"modify_comment": 4, "modify_type": 1})
    assert not at_86 - _difference_kinds(upgrade_db)

    alembic_chain.upgrade(upgrade_db, "head")
    assert alembic_chain.schema_differences(upgrade_db) == []


def test_revision_85_is_irreversible(upgrade_db):
    alembic_chain.upgrade(upgrade_db, _REVISION_86)
    alembic_chain.downgrade(upgrade_db, _REVISION_85)

    with pytest.raises(NotImplementedError):
        alembic_chain.downgrade(upgrade_db, _REVISION_84)

    assert _scalar(upgrade_db, "SELECT version_num FROM alembic_version") == _REVISION_85


def test_revision_87_is_irreversible(upgrade_db):
    alembic_chain.upgrade(upgrade_db, "head")

    with pytest.raises(NotImplementedError):
        alembic_chain.downgrade(upgrade_db, _REVISION_86)

    assert _scalar(upgrade_db, "SELECT version_num FROM alembic_version") == _REVISION_87


def test_revision_87_gives_the_leaf_tables_uuid_primary_keys(upgrade_db):
    alembic_chain.upgrade(upgrade_db, alembic_chain.V0_20_HEAD)
    _seed(upgrade_db, alembic_chain.seed_v0_20)
    alembic_chain.upgrade(upgrade_db, _REVISION_84)
    _seed(upgrade_db, alembic_chain.seed_v0_21)
    alembic_chain.upgrade(upgrade_db, _REVISION_86)
    counts_before = alembic_chain.row_counts(upgrade_db)
    goals_before = _rows(upgrade_db, "SELECT goal_distance FROM users_goals ORDER BY id")
    followers_before = _rows(upgrade_db, "SELECT follower_id, followee_id FROM followers ORDER BY id")
    blocks_before = _rows(upgrade_db, "SELECT blocker_id, blocked_id FROM follower_blocks ORDER BY id")
    assert [row[0] for row in goals_before] == [10000, 20000, 30000]
    assert followers_before == [(1, 2), (3, 1), (2, 1)]
    assert blocks_before == [(2, 3), (1, 2), (1, 3)]

    alembic_chain.upgrade(upgrade_db, "head")

    assert alembic_chain.row_counts(upgrade_db) == {**counts_before, _TABLE_EMPTIED_BY_REVISION_87: 0}
    assert _columns_of_type(upgrade_db, "uuid", ("id",)) == [(table, "id") for table in sorted(_REVISION_87_TABLES)]
    assert _data_type(upgrade_db, _TABLE_EMPTIED_BY_REVISION_87, "record_id") == "uuid"
    assert [table for table, _ in _columns_of_type(upgrade_db, "integer", ("record_id",))] == sorted(
        _KEPT_TOMBSTONE_TABLES
    )
    other_keys = ("user_id", "idp_id", "follower_id", "followee_id", "blocker_id", "blocked_id")
    assert _columns_of_type(upgrade_db, "uuid", other_keys) == []
    assert _data_type(upgrade_db, "users_default_gear", "ride_gear_id") == "integer"
    assert _data_type(upgrade_db, "users_default_gear", "user_id") == "integer"
    with upgrade_db.connect() as connection:
        for table in _REVISION_87_TABLES:
            rows = sa.table(table, sa.column("id"))
            distinct = connection.execute(sa.select(sa.func.count(sa.distinct(rows.c.id)))).scalar_one()
            expected = 0 if table == _TABLE_EMPTIED_BY_REVISION_87 else counts_before[table]
            assert distinct == expected
    assert _rows(upgrade_db, "SELECT goal_distance FROM users_goals ORDER BY created_at, id") == goals_before
    assert _data_type(upgrade_db, "users_goals", "created_at") == "timestamp with time zone"
    assert (
        _scalar(
            upgrade_db,
            "SELECT is_nullable FROM information_schema.columns "
            "WHERE table_name = 'users_goals' AND column_name = 'created_at'",
        )
        == "NO"
    )
    assert (
        _rows(upgrade_db, "SELECT follower_id, followee_id FROM followers ORDER BY created_at, id") == followers_before
    )
    assert (
        _rows(upgrade_db, "SELECT blocker_id, blocked_id FROM follower_blocks ORDER BY created_at, id") == blocks_before
    )
    created_at_steps = _rows(upgrade_db, "SELECT created_at - MIN(created_at) OVER () FROM followers ORDER BY 1")
    assert [step[0] for step in created_at_steps] == [
        timedelta(0),
        timedelta(microseconds=1),
        timedelta(microseconds=2),
    ]
    with upgrade_db.connect() as connection:
        for table in _KEPT_TOMBSTONE_TABLES:
            rows = sa.table(table, sa.column("record_id"))
            assert connection.execute(sa.select(rows.c.record_id)).scalars().all() == [100]
    assert alembic_chain.schema_differences(upgrade_db) == []
    alembic_chain.bootstrap_substrate(upgrade_db)
    assert alembic_chain.schema_differences(upgrade_db) == []
