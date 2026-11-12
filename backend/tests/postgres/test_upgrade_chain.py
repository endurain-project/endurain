"""The real Alembic chain, run against an empty database and against a seeded v0.20.x install."""

import json
import uuid
from collections import Counter
from datetime import timedelta
from unittest.mock import patch

import pytest
import sqlalchemy as sa
from jasil.backends.storage_local import LocalStorage
from sqlalchemy.dialects import postgresql
from sqlalchemy.orm import Session

import migrations.migration_13 as migration_13
from tests._helpers import alembic_chain

_REVISION_0 = "c5cfe02a11c2"
_REVISION_84 = "b84e9f3a6c25"
_REVISION_85 = "b41c0afdc9d9"
_REVISION_86 = "3e7a91d4c0b8"
_REVISION_87 = "e05703e64861"
_REVISION_88 = "dc5f0450aaf0"
_REVISION_89 = "ecaa46b32646"
_REVISION_90 = "3ab6649cdd08"
_RETIRED_DATA_MIGRATIONS = {1, 2, 3, 4, 5, 6, 8, 9, 10}
_UNPREFIXED_SUBSTRATE_TABLES = ("event_log", "event_outbox", "processing_jobs")
#: The tables the chain empties by design: their record ids name rows whose ids change (revisions 87, 89 and 90).
_TABLES_EMPTIED_BY_THE_CHAIN = {
    "health_record_deletions",
    "gear_deletions",
    "gear_component_deletions",
    "activity_deletions",
}
#: The one table revision 87 empties.
_TABLE_EMPTIED_BY_REVISION_87 = "health_record_deletions"
#: The tombstone tables revision 89 empties.
_TABLES_EMPTIED_BY_REVISION_89 = ("gear_deletions", "gear_component_deletions")
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
    assert {name for name, count in counts.items() if count == 0} == _TABLES_EMPTIED_BY_THE_CHAIN
    for name in _TABLES_EMPTIED_BY_THE_CHAIN:
        counts.pop(name)
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
    assert _migrations_state(upgrade_db) == {7: True, 11: False, 12: False, 13: False}
    assert _scalar(upgrade_db, "SELECT count(*) FROM uuid_migration_ids") == 0
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
    assert after == {
        **before,
        "migrations": before["migrations"] - 9 + 1,
        **dict.fromkeys(_TABLES_EMPTIED_BY_THE_CHAIN, 0),
    }
    assert set(_migrations_state(upgrade_db)) == {7, 11, 12, 13}
    assert _scalar(upgrade_db, "SELECT to_regclass('cadence_spm_migration_rows')") is None
    assert _scalar(upgrade_db, "SELECT start_time FROM activity_sets WHERE duration = 30").isoformat() == (
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
    alembic_chain.upgrade(upgrade_db, _REVISION_87)

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

    alembic_chain.upgrade(upgrade_db, _REVISION_88)

    assert alembic_chain.row_counts(upgrade_db) == {
        **counts_before,
        "migrations": counts_before["migrations"] + 1,
        _TABLE_EMPTIED_BY_REVISION_87: 0,
    }
    assert _columns_of_type(upgrade_db, "uuid", ("id",)) == [(table, "id") for table in sorted(_REVISION_87_TABLES)]
    assert _data_type(upgrade_db, _TABLE_EMPTIED_BY_REVISION_87, "record_id") == "uuid"
    assert [table for table, _ in _columns_of_type(upgrade_db, "integer", ("record_id",))] == sorted(
        _KEPT_TOMBSTONE_TABLES
    )
    other_keys = ("user_id", "follower_id", "followee_id", "blocker_id", "blocked_id")
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
    alembic_chain.upgrade(upgrade_db, "head")
    assert alembic_chain.schema_differences(upgrade_db) == []
    alembic_chain.bootstrap_substrate(upgrade_db)
    assert alembic_chain.schema_differences(upgrade_db) == []


_IDP_REFERENCES = (
    ("users_identity_providers", "user_id"),
    ("idp_session_tokens", "session_id"),
    ("oauth_states", "id"),
)
_IDP_PAIRS = {1: "seed-provider", 2: "second-provider"}
_JSON_PAYLOAD_COLUMNS = {
    "event_outbox": ("payload", "event_metadata"),
    "processing_jobs": ("payload", "job_metadata"),
    "event_log": ("event_payload", "event_metadata"),
}
_REWRITTEN_EVENT_TYPES = ("auth.idp_linked", "auth.account_security_changed")


def _provider_pairs(engine, table: str, key: str) -> list[tuple]:
    """Return (key, slug of the provider it references) of every row, whatever the type of the id."""
    rows = sa.table(table, sa.column(key), sa.column("idp_id"))
    providers = sa.table("identity_providers", sa.column("id"), sa.column("slug"))
    statement = (
        sa.select(rows.c[key], providers.c.slug)
        .select_from(rows.outerjoin(providers, providers.c.id == rows.c.idp_id))
        .order_by(rows.c[key])
    )
    with engine.connect() as connection:
        return [tuple(row) for row in connection.execute(statement)]


def _count_joined_to_providers(engine, table: str) -> int:
    rows = sa.table(table, sa.column("idp_id"))
    providers = sa.table("identity_providers", sa.column("id"))
    with engine.connect() as connection:
        return connection.execute(
            sa.select(sa.func.count()).select_from(rows.join(providers, providers.c.id == rows.c.idp_id))
        ).scalar_one()


def _seed_to_87(engine):
    alembic_chain.upgrade(engine, alembic_chain.V0_20_HEAD)
    _seed(engine, alembic_chain.seed_v0_20)
    alembic_chain.upgrade(engine, _REVISION_84)
    _seed(engine, alembic_chain.seed_v0_21)
    alembic_chain.upgrade(engine, _REVISION_87)


def _new_ids_by_slug(engine) -> dict[str, str]:
    return dict(_rows(engine, "SELECT slug, id::text FROM identity_providers"))


def _seeded_rows(engine, table: str, *columns: str, id_prefix: str = "idp") -> list[tuple]:
    """Return the given columns of the rows a seeder added to a substrate table, by id; the ids start with the prefix."""
    rows = sa.table(table, sa.column("id"), *(sa.column(name) for name in columns))
    statement = (
        sa.select(*(rows.c[name] for name in columns), rows.c.id)
        .where(rows.c.id.like(f"{id_prefix}-%"))
        .order_by(rows.c.id)
    )
    with engine.connect() as connection:
        return [tuple(row) for row in connection.execute(statement)]


def _assert_events_rewritten(engine, prefix: str, new_ids: dict[str, str]) -> None:
    """Check every seeded row of the substrate tables: payload ids rewritten, controls and metadata untouched."""
    old_to_new = {old: new_ids[slug] for old, slug in _IDP_PAIRS.items()}
    expected_rows = {"event_outbox": 10, "processing_jobs": 25, "event_log": 5}
    for table, (payload_column, metadata_column) in _JSON_PAYLOAD_COLUMNS.items():
        rows = _seeded_rows(engine, f"{prefix}{table}", "event_type", payload_column, metadata_column)
        assert len(rows) == expected_rows[table]
        for event_type, payload, metadata, row_id in rows:
            old_payload = alembic_chain.IDP_EVENT_CASES[int(row_id.split("-")[2])][1]
            assert metadata == alembic_chain.IDP_EVENT_METADATA
            if event_type == "activity.created":
                assert payload == old_payload
                continue
            assert {key: value for key, value in payload.items() if key != "idp_id"} == {
                key: value for key, value in old_payload.items() if key != "idp_id"
            }
            old_idp = old_payload["idp_id"]
            if old_idp is None:
                assert payload["idp_id"] is None
            elif old_idp in old_to_new:
                assert payload["idp_id"] == old_to_new[old_idp]
            else:
                assert str(uuid.UUID(payload["idp_id"])) == payload["idp_id"]
                assert payload["idp_id"] not in new_ids.values()


def _assert_job_states_covered(engine, prefix: str, id_prefix: str = "idp") -> None:
    jobs = _seeded_rows(engine, f"{prefix}processing_jobs", "status", "attempts", id_prefix=id_prefix)
    assert {(status, attempts > 0) for status, attempts, _ in jobs} == {
        ("claimed", False),
        ("completed", False),
        ("dead_letter", False),
        ("pending", False),
        ("pending", True),
    }
    relayed = _seeded_rows(engine, f"{prefix}event_outbox", "relayed_at", id_prefix=id_prefix)
    assert {relayed_at is None for relayed_at, _ in relayed} == {True, False}


def test_revision_88_converts_identity_providers_and_their_references(upgrade_db):
    _seed_to_87(upgrade_db)
    counts_before = alembic_chain.row_counts(upgrade_db)
    old_ids = dict(_rows(upgrade_db, "SELECT slug, id FROM identity_providers"))
    assert old_ids == {slug: old for old, slug in _IDP_PAIRS.items()}
    pairs_before = {table: _provider_pairs(upgrade_db, table, key) for table, key in _IDP_REFERENCES}
    assert pairs_before["oauth_states"] == [
        ("seed-oauth-state", "seed-provider"),
        ("seed-oauth-state-2", "second-provider"),
        ("seed-oauth-state-no-idp", None),
    ]
    _assert_job_states_covered(upgrade_db, "")
    control_before = _rows(
        upgrade_db, "SELECT id, event_payload FROM event_log WHERE event_type = 'activity.created' ORDER BY id"
    )

    alembic_chain.upgrade(upgrade_db, _REVISION_88)

    assert alembic_chain.row_counts(upgrade_db) == {**counts_before, "migrations": counts_before["migrations"] + 1}
    for table, column in (
        ("identity_providers", "id"),
        ("users_identity_providers", "idp_id"),
        ("idp_session_tokens", "idp_id"),
        ("oauth_states", "idp_id"),
    ):
        assert _data_type(upgrade_db, table, column) == "uuid"
    new_ids = _new_ids_by_slug(upgrade_db)
    assert len(set(new_ids.values())) == 2
    assert {table: _provider_pairs(upgrade_db, table, key) for table, key in _IDP_REFERENCES} == pairs_before
    for table in ("users_identity_providers", "idp_session_tokens"):
        assert _count_joined_to_providers(upgrade_db, table) == alembic_chain.row_counts(upgrade_db)[table]
    assert _rows(upgrade_db, "SELECT idp_id FROM oauth_states WHERE id = 'seed-oauth-state-no-idp'") == [(None,)]

    _assert_events_rewritten(upgrade_db, "", new_ids)
    assert _rows(
        upgrade_db, "SELECT id, event_payload FROM event_log WHERE event_type = 'activity.created' ORDER BY id"
    ) == [row for row in control_before]

    notifications = {
        row[0]: row[1]
        for row in _rows(upgrade_db, "SELECT id::text, options::jsonb FROM notifications WHERE type IN (31, 32)")
    }
    options = sorted(notifications.values(), key=lambda document: json.dumps(document, sort_keys=True))
    assert {"idp_id": new_ids["second-provider"], "idp_name": "Second"} in options
    assert {
        "change": "identity_provider_unlinked",
        "idp_id": new_ids["seed-provider"],
        "idp_name": "Seed Provider",
    } in options
    assert {"change": "password_changed", "idp_id": None} in options
    dangling = next(document for document in options if document.get("idp_name", "") is None)
    assert str(uuid.UUID(dangling["idp_id"])) == dangling["idp_id"]
    assert dangling["idp_id"] not in new_ids.values()
    assert _rows(
        upgrade_db,
        "SELECT options::jsonb FROM notifications WHERE source_event_id = '55555555-5555-4555-8555-555555555555'",
    ) == [({"activity_id": 1},)]

    assert sorted(_rows(upgrade_db, "SELECT table_name, old_id, new_id::text FROM uuid_migration_ids")) == sorted(
        ("identity_providers", old_ids[slug], new_ids[slug]) for slug in old_ids
    )
    assert _migrations_state(upgrade_db)[13] is False
    alembic_chain.upgrade(upgrade_db, "head")
    assert alembic_chain.schema_differences(upgrade_db) == []
    alembic_chain.bootstrap_substrate(upgrade_db)
    assert alembic_chain.schema_differences(upgrade_db) == []

    with upgrade_db.begin() as connection:
        connection.execute(sa.text("DELETE FROM identity_providers WHERE slug = 'second-provider'"))
    assert _provider_pairs(upgrade_db, "users_identity_providers", "user_id") == [(1, "seed-provider")]
    assert _provider_pairs(upgrade_db, "idp_session_tokens", "session_id") == [
        ("33333333-3333-4333-8333-333333333333", "seed-provider")
    ]
    assert _provider_pairs(upgrade_db, "oauth_states", "id") == [
        ("seed-oauth-state", "seed-provider"),
        ("seed-oauth-state-no-idp", None),
    ]


def test_revision_88_rewrites_the_jasil_prefixed_substrate_tables(upgrade_db):
    alembic_chain.upgrade(upgrade_db, alembic_chain.V0_20_HEAD)
    _seed(upgrade_db, alembic_chain.seed_v0_20)
    alembic_chain.upgrade(upgrade_db, _REVISION_84)
    _seed(upgrade_db, alembic_chain.seed_v0_21)
    alembic_chain.upgrade(upgrade_db, _REVISION_87)
    with upgrade_db.begin() as connection:
        for table in _UNPREFIXED_SUBSTRATE_TABLES:
            rows = sa.table(table, sa.column("id"))
            connection.execute(sa.delete(rows).where(rows.c.id.like("idp-%")))
    alembic_chain.bootstrap_substrate(upgrade_db)
    assert _scalar(upgrade_db, "SELECT to_regclass('event_outbox')") is None
    _seed(
        upgrade_db,
        lambda connection: alembic_chain.seed_events(
            connection,
            alembic_chain.IDP_EVENT_CASES,
            alembic_chain.IDP_EVENT_METADATA,
            alembic_chain.IDP_EVENT_PREFIX,
            "jasil_",
        ),
    )
    _assert_job_states_covered(upgrade_db, "jasil_")

    alembic_chain.upgrade(upgrade_db, _REVISION_88)

    _assert_events_rewritten(upgrade_db, "jasil_", _new_ids_by_slug(upgrade_db))
    alembic_chain.upgrade(upgrade_db, "head")
    assert alembic_chain.schema_differences(upgrade_db) == []
    alembic_chain.bootstrap_substrate(upgrade_db)
    assert alembic_chain.schema_differences(upgrade_db) == []


def test_revision_88_is_irreversible(upgrade_db):
    alembic_chain.upgrade(upgrade_db, _REVISION_88)

    with pytest.raises(NotImplementedError):
        alembic_chain.downgrade(upgrade_db, _REVISION_87)

    assert _scalar(upgrade_db, "SELECT version_num FROM alembic_version") == _REVISION_88


_GEAR_REFERENCES = (
    ("activities", "gear_id"),
    ("gear_components", "gear_id"),
    *(
        ("users_default_gear", f"{activity_type}_gear_id")
        for activity_type in (
            "run",
            "trail_run",
            "virtual_run",
            "ride",
            "gravel_ride",
            "mtb_ride",
            "virtual_ride",
            "ows",
            "walk",
            "hike",
            "tennis",
            "alpine_ski",
            "nordic_ski",
            "snowboard",
            "windsurf",
        )
    ),
)
_GEAR_RECORD_ID_TABLES = ("gear_deletions", "gear_component_deletions")


#: The column that identifies a row of each referencing table across the conversion: ``gear_components`` gets new ids.
_GEAR_ROW_KEYS = {"activities": "id", "gear_components": "type", "users_default_gear": "user_id"}


def _gear_pairs(engine, table: str, column: str) -> list[tuple]:
    """Return (row key, nickname of the gear the column references) of every row, whatever the type of the ids."""
    key = _GEAR_ROW_KEYS[table]
    rows = sa.table(table, sa.column(key), sa.column(column))
    gear = sa.table("gear", sa.column("id"), sa.column("nickname"))
    statement = (
        sa.select(rows.c[key], gear.c.nickname)
        .select_from(rows.outerjoin(gear, gear.c.id == rows.c[column]))
        .order_by(rows.c[key])
    )
    with engine.connect() as connection:
        return [tuple(row) for row in connection.execute(statement)]


def _count_not_null(engine, table: str, column: str) -> int:
    rows = sa.table(table, sa.column(column))
    with engine.connect() as connection:
        return connection.execute(sa.select(sa.func.count(rows.c[column]))).scalar_one()


def _count_joined_to_gear(engine, table: str, column: str) -> int:
    rows = sa.table(table, sa.column(column))
    gear = sa.table("gear", sa.column("id"))
    with engine.connect() as connection:
        return connection.execute(
            sa.select(sa.func.count()).select_from(rows.join(gear, gear.c.id == rows.c[column]))
        ).scalar_one()


def _substrate_rows(engine) -> dict[str, list[tuple]]:
    """Return every row of the three unprefixed substrate tables, whole and ordered by id."""
    with engine.connect() as connection:
        return {
            table: [
                tuple(row)
                for row in connection.execute(
                    sa.select(sa.text("*")).select_from(sa.table(table)).order_by(sa.column("id"))
                )
            ]
            for table in _UNPREFIXED_SUBSTRATE_TABLES
        }


def test_revision_89_converts_gear_and_its_references(upgrade_db):
    _seed_to_87(upgrade_db)
    alembic_chain.upgrade(upgrade_db, _REVISION_88)
    counts_before = alembic_chain.row_counts(upgrade_db)
    pairs_before = {(table, column): _gear_pairs(upgrade_db, table, column) for table, column in _GEAR_REFERENCES}
    for table, column in _GEAR_REFERENCES:
        pairs = pairs_before[(table, column)]
        assert any(nickname is not None for _, nickname in pairs), (table, column)
        if table != "gear_components":
            assert any(nickname is None for _, nickname in pairs), (table, column)
    components_before = _rows(upgrade_db, "SELECT type, brand FROM gear_components ORDER BY id")
    assert len(components_before) == 4
    assert _rows(upgrade_db, "SELECT type FROM gear_components ORDER BY purchase_date") != [
        (kind,) for kind, _ in components_before
    ]
    providers_before = _rows(
        upgrade_db, "SELECT nickname, strava_gear_id, garminconnect_gear_id FROM gear ORDER BY nickname"
    )
    assert ("Second bike", "b12345", "garmin-gear-2") in providers_before
    substrate_before = _substrate_rows(upgrade_db)
    migration_ids_before = _rows(upgrade_db, "SELECT table_name, old_id, new_id::text FROM uuid_migration_ids")
    migrations_before = _migrations_state(upgrade_db)

    alembic_chain.upgrade(upgrade_db, _REVISION_89)

    assert alembic_chain.row_counts(upgrade_db) == {
        **counts_before,
        "migrations": counts_before["migrations"],
        **dict.fromkeys(_GEAR_RECORD_ID_TABLES, 0),
    }
    uuid_columns = [("gear", "id"), ("gear_components", "id"), *_GEAR_REFERENCES]
    uuid_columns += [(table, "record_id") for table in _GEAR_RECORD_ID_TABLES]
    for table, column in uuid_columns:
        assert _data_type(upgrade_db, table, column) == "uuid", (table, column)
    assert _data_type(upgrade_db, "activities", "id") == "integer"
    for table in ("gear", "gear_components", "users_default_gear", "activities"):
        assert _data_type(upgrade_db, table, "user_id") == "integer"
    assert _scalar(upgrade_db, "SELECT count(DISTINCT id) FROM gear") == 3
    assert _scalar(upgrade_db, "SELECT count(DISTINCT id) FROM gear_components") == 4
    assert {(table, column): _gear_pairs(upgrade_db, table, column) for table, column in _GEAR_REFERENCES} == (
        pairs_before
    )
    for table, column in _GEAR_REFERENCES:
        assert _count_joined_to_gear(upgrade_db, table, column) == _count_not_null(upgrade_db, table, column)
    assert _rows(upgrade_db, "SELECT type, brand FROM gear_components ORDER BY created_at, id") == components_before
    assert _data_type(upgrade_db, "gear_components", "created_at") == "timestamp with time zone"
    assert (
        _scalar(
            upgrade_db,
            "SELECT is_nullable FROM information_schema.columns "
            "WHERE table_name = 'gear_components' AND column_name = 'created_at'",
        )
        == "NO"
    )
    steps = _rows(upgrade_db, "SELECT created_at - MIN(created_at) OVER () FROM gear_components ORDER BY 1")
    assert [step[0] for step in steps] == [timedelta(microseconds=index) for index in range(4)]
    assert (
        _rows(upgrade_db, "SELECT nickname, strava_gear_id, garminconnect_gear_id FROM gear ORDER BY nickname")
        == providers_before
    )
    assert _substrate_rows(upgrade_db) == substrate_before
    assert _rows(upgrade_db, "SELECT table_name, old_id, new_id::text FROM uuid_migration_ids") == migration_ids_before
    assert _migrations_state(upgrade_db) == migrations_before
    alembic_chain.upgrade(upgrade_db, "head")
    assert alembic_chain.schema_differences(upgrade_db) == []
    alembic_chain.bootstrap_substrate(upgrade_db)
    assert alembic_chain.schema_differences(upgrade_db) == []

    with upgrade_db.begin() as connection:
        connection.execute(sa.text("DELETE FROM gear WHERE nickname = 'Second bike'"))
    assert _scalar(upgrade_db, "SELECT gear_id FROM activities WHERE name = 'Ride on second bike'") is None
    assert _scalar(upgrade_db, "SELECT count(*) FROM gear_components") == 2
    for table, column in _GEAR_REFERENCES:
        assert _count_joined_to_gear(upgrade_db, table, column) == _count_not_null(upgrade_db, table, column)
    assert _scalar(upgrade_db, "SELECT trail_run_gear_id FROM users_default_gear WHERE user_id = 1") is None
    assert _scalar(upgrade_db, "SELECT run_gear_id FROM users_default_gear WHERE user_id = 1") is not None


def test_revision_89_is_irreversible(upgrade_db):
    alembic_chain.upgrade(upgrade_db, _REVISION_89)

    with pytest.raises(NotImplementedError):
        alembic_chain.downgrade(upgrade_db, _REVISION_88)

    assert _scalar(upgrade_db, "SELECT version_num FROM alembic_version") == _REVISION_89


_ACTIVITY_CHILDREN = (
    "activity_laps",
    "activity_media",
    "activity_sets",
    "activities_streams",
    "activity_workout_steps",
)
_ACTIVITY_NAMES = {1: "Seed ride", 2: "Ride without gear", 3: "Ride on second bike"}
#: The column that identifies a row of each child table across the conversion, as a SQL expression.
_ACTIVITY_CHILD_KEYS = {
    "activity_laps": "start_time",
    "activity_media": "media_path",
    "activity_sets": "duration",
    "activities_streams": "stream_waypoints",
    "activity_workout_steps": "message_index",
}
#: The order of each child table that the old integer ids gave and the new sort must keep.
_ACTIVITY_CHILD_ORDERS = {
    "activity_laps": ("start_time", "start_time"),
    "activity_sets": ("duration", "start_time"),
    "activity_workout_steps": ("message_index", "message_index"),
    "activity_media": ("media_path", "created_at"),
}
_ACTIVITY_PROVIDER_ID_COLUMNS = (
    ("activities", "strava_activity_id"),
    ("activities", "garminconnect_activity_id"),
    ("activities_streams", "strava_activity_stream_id"),
)
_ACTIVITY_EVENT_ROWS = {"event_outbox": 8, "processing_jobs": 20, "event_log": 4}


def _activity_pairs(engine, table: str) -> list[tuple]:
    """Return (key, name of the activity it references) of every row of a child table, whatever the type of the ids."""
    rows = sa.table(table, sa.column(_ACTIVITY_CHILD_KEYS[table]), sa.column("activity_id"))
    activities = sa.table("activities", sa.column("id"), sa.column("name"))
    key = sa.cast(rows.c[_ACTIVITY_CHILD_KEYS[table]], sa.Text)
    statement = (
        sa.select(key, activities.c.name)
        .select_from(rows.outerjoin(activities, activities.c.id == rows.c.activity_id))
        .order_by(key, activities.c.name)
    )
    with engine.connect() as connection:
        return [tuple(row) for row in connection.execute(statement)]


def _count_joined_to_activities(engine, table: str) -> int:
    rows = sa.table(table, sa.column("activity_id"))
    activities = sa.table("activities", sa.column("id"))
    with engine.connect() as connection:
        return connection.execute(
            sa.select(sa.func.count()).select_from(rows.join(activities, activities.c.id == rows.c.activity_id))
        ).scalar_one()


def _table_count(engine, table: str, *measure: str) -> int:
    """Count the rows of a table, the distinct values of a column (``distinct``) or its non-null values (``not_null``)."""
    rows = sa.table(table, sa.column("id"), sa.column("activity_id"))
    with engine.connect() as connection:
        match measure:
            case ("distinct", name):
                expression = sa.func.count(sa.distinct(rows.c[name]))
            case ("not_null", name):
                expression = sa.func.count(rows.c[name])
            case _:
                expression = sa.func.count()
        return connection.execute(sa.select(expression).select_from(rows)).scalar_one()


def _column_in_order(engine, table: str, column: str, order_by: str) -> list[tuple]:
    """Return one column of a table ordered by another column and then by id."""
    rows = sa.table(table, sa.column("id"), sa.column(column), sa.column(order_by))
    with engine.connect() as connection:
        return [
            tuple(row) for row in connection.execute(sa.select(rows.c[column]).order_by(rows.c[order_by], rows.c.id))
        ]


#: The notification id of each seeded source event id, by its last digit.
_ACTIVITY_NOTIFICATION_IDS = {"5": 1, "6": 6, "7": 7}


def _activity_notifications(engine) -> dict[int, dict]:
    """Return the options of notifications 1, 6 and 7, found by the last digit of their source event id."""
    return {
        _ACTIVITY_NOTIFICATION_IDS[source_event_id[-1]]: options
        for source_event_id, options in _rows(
            engine,
            "SELECT source_event_id, options::jsonb FROM notifications "
            "WHERE source_event_id LIKE '55555555-5555-4555-8555-55555555555%'",
        )
    }


def _new_activity_ids(engine) -> dict[int, str]:
    """Return the UUID of each seeded activity by its old integer id, as ``uuid_migration_ids`` recorded it."""
    return dict(_rows(engine, "SELECT old_id, new_id::text FROM uuid_migration_ids WHERE table_name = 'activities'"))


def _assert_activity_events_rewritten(engine, prefix: str, new_ids: dict[int, str]) -> None:
    """Check every seeded activity event row: ``activity_id`` rewritten by event type, controls and user ids kept."""
    for table, (payload_column, metadata_column) in _JSON_PAYLOAD_COLUMNS.items():
        rows = _seeded_rows(engine, f"{prefix}{table}", "event_type", payload_column, metadata_column, id_prefix="act")
        assert len(rows) == _ACTIVITY_EVENT_ROWS[table]
        for event_type, payload, metadata, row_id in rows:
            old_payload = alembic_chain.ACTIVITY_EVENT_CASES[int(row_id.split("-")[2])][1]
            assert metadata == {**alembic_chain.ACTIVITY_EVENT_METADATA, "activity_id": new_ids[1]}
            if event_type == "auth.idp_linked":
                # Revision 88 rewrites its idp_id when the row exists then; revision 90 leaves the activity_id alone.
                assert {key: value for key, value in payload.items() if key != "idp_id"} == {
                    key: value for key, value in old_payload.items() if key != "idp_id"
                }
                continue
            assert {key: value for key, value in payload.items() if key != "activity_id"} == {
                key: value for key, value in old_payload.items() if key != "activity_id"
            }
            old_activity = old_payload["activity_id"]
            if old_activity in new_ids:
                assert payload["activity_id"] == new_ids[old_activity]
            else:
                assert str(uuid.UUID(payload["activity_id"])) == payload["activity_id"]
                assert payload["activity_id"] not in new_ids.values()
            assert payload.get("user_id", 1) == 1
    log = sa.table(f"{prefix}event_log", sa.column("id"), sa.column("event_payload", postgresql.JSONB))
    with engine.connect() as connection:
        legacy = (
            connection.execute(
                sa.select(log.c.event_payload)
                .where(log.c.id.in_(["77777777-7777-4777-8777-777777777777", "idp-event-4"]))
                .order_by(log.c.id)
            )
            .scalars()
            .all()
        )
    assert [payload["activity_id"] for payload in legacy] == [new_ids[1], new_ids[1]]
    assert legacy[1]["idp_id"] == 2


def test_revision_90_converts_activities_and_their_children(upgrade_db):
    _seed_to_87(upgrade_db)
    alembic_chain.upgrade(upgrade_db, _REVISION_89)
    counts_before = alembic_chain.row_counts(upgrade_db)
    migrations_before = _migrations_state(upgrade_db)
    idp_ids_before = _rows(upgrade_db, "SELECT table_name, old_id, new_id::text FROM uuid_migration_ids")
    assert len(idp_ids_before) == 2
    provider_types = {column: _data_type(upgrade_db, *column) for column in _ACTIVITY_PROVIDER_ID_COLUMNS}
    provider_values = _rows(
        upgrade_db, "SELECT strava_activity_id, garminconnect_activity_id FROM activities ORDER BY 1"
    )
    assert provider_values[0] == (12345, 67890)
    assert (
        _scalar(upgrade_db, "SELECT strava_activity_stream_id FROM activities_streams WHERE stream_type = 2 AND id = 2")
        == 555
    )
    pairs_before = {table: _activity_pairs(upgrade_db, table) for table in _ACTIVITY_CHILDREN}
    for table, pairs in pairs_before.items():
        assert {name for _, name in pairs} >= {"Seed ride"}, table
    gear_before = _rows(
        upgrade_db, "SELECT a.name, g.nickname FROM activities a LEFT JOIN gear g ON g.id = a.gear_id ORDER BY a.name"
    )
    assert gear_before == [
        ("Ride on second bike", "Second bike"),
        ("Ride without gear", None),
        ("Seed ride", "Seed bike"),
    ]
    orders_before = {
        table: _column_in_order(upgrade_db, table, id_key, "id")
        for table, (id_key, _) in _ACTIVITY_CHILD_ORDERS.items()
    }
    assert orders_before["activity_media"] == [
        ("seed/media.jpg",),
        ("1_bbb.jpg",),
        ("1_ccc.jpg",),
        ("1_aaa.jpg",),
        ("3_ddd.jpg",),
    ]
    thumbnails_before = _rows(upgrade_db, "SELECT name, map_thumbnail_path FROM activities ORDER BY name")
    assert thumbnails_before == [
        ("Ride on second bike", "3.webp"),
        ("Ride without gear", None),
        ("Seed ride", "1.webp"),
    ]
    titles_before = _rows(upgrade_db, "SELECT id, wkt_step_name FROM activity_exercise_titles")
    idp_notifications_before = _rows(upgrade_db, "SELECT id, options::jsonb FROM notifications WHERE type IN (31, 32)")
    old_notifications = _activity_notifications(upgrade_db)
    assert old_notifications[7] == {"activity_id": 999}
    jobs_before = dict(_rows(upgrade_db, "SELECT id::text, activity_ids::jsonb FROM activity_ingestion_jobs"))
    assert sorted(jobs_before.values(), key=str) == sorted([[1], [1, 3], [3, 999], [], None], key=str)
    _assert_job_states_covered(upgrade_db, "", "act")
    idp_events_before = {
        table: _seeded_rows(upgrade_db, table, payload, metadata)
        for table, (payload, metadata) in _JSON_PAYLOAD_COLUMNS.items()
    }

    alembic_chain.upgrade(upgrade_db, _REVISION_90)

    for table in ("activities", *_ACTIVITY_CHILDREN):
        assert _data_type(upgrade_db, table, "id") == "uuid", table
    for table in _ACTIVITY_CHILDREN:
        assert _data_type(upgrade_db, table, "activity_id") == "uuid", table
    assert _data_type(upgrade_db, "activity_deletions", "record_id") == "uuid"
    for table in ("activities", "activity_deletions"):
        assert _data_type(upgrade_db, table, "user_id") == "integer"
    assert _data_type(upgrade_db, "activity_exercise_titles", "id") == "integer"
    assert {column: _data_type(upgrade_db, *column) for column in _ACTIVITY_PROVIDER_ID_COLUMNS} == provider_types
    assert (
        _rows(upgrade_db, "SELECT strava_activity_id, garminconnect_activity_id FROM activities ORDER BY 1")
        == provider_values
    )
    assert (
        _scalar(
            upgrade_db, "SELECT strava_activity_stream_id FROM activities_streams WHERE strava_activity_stream_id = 555"
        )
        == 555
    )
    assert _rows(upgrade_db, "SELECT id, wkt_step_name FROM activity_exercise_titles") == titles_before
    assert alembic_chain.row_counts(upgrade_db) == {**counts_before, "activity_deletions": 0}
    assert _migrations_state(upgrade_db) == migrations_before
    for table in ("activities", *_ACTIVITY_CHILDREN):
        assert _table_count(upgrade_db, table, "distinct", "id") == counts_before[table], table

    for table in _ACTIVITY_CHILDREN:
        assert _activity_pairs(upgrade_db, table) == pairs_before[table], table
        not_null = _table_count(upgrade_db, table, "not_null", "activity_id")
        assert _count_joined_to_activities(upgrade_db, table) == not_null, table
    assert (
        _rows(
            upgrade_db,
            "SELECT a.name, g.nickname FROM activities a LEFT JOIN gear g ON g.id = a.gear_id ORDER BY a.name",
        )
        == gear_before
    )

    for table, (id_key, sort_key) in _ACTIVITY_CHILD_ORDERS.items():
        assert _column_in_order(upgrade_db, table, id_key, sort_key) == orders_before[table], table
    assert _data_type(upgrade_db, "activity_media", "created_at") == "timestamp with time zone"
    assert (
        _scalar(
            upgrade_db,
            "SELECT is_nullable FROM information_schema.columns "
            "WHERE table_name = 'activity_media' AND column_name = 'created_at'",
        )
        == "NO"
    )
    steps = _rows(upgrade_db, "SELECT created_at - MIN(created_at) OVER () FROM activity_media ORDER BY 1")
    assert [step[0] for step in steps] == [timedelta(microseconds=index) for index in range(5)]
    assert _rows(upgrade_db, "SELECT name, map_thumbnail_path FROM activities ORDER BY name") == thumbnails_before

    new_ids = _new_activity_ids(upgrade_db)
    assert {_ACTIVITY_NAMES[old]: new for old, new in new_ids.items()} == dict(
        _rows(upgrade_db, "SELECT name, id::text FROM activities")
    )
    assert len(set(new_ids.values())) == 3
    for table in ("activities", *_ACTIVITY_CHILDREN):
        with upgrade_db.connect() as connection:
            ids = connection.execute(sa.select(sa.cast(sa.column("id"), sa.Text)).select_from(sa.table(table)))
            assert {uuid.UUID(value).version for (value,) in ids} == {4}, table
    assert sorted(_rows(upgrade_db, "SELECT table_name, old_id, new_id::text FROM uuid_migration_ids")) == sorted(
        [*idp_ids_before, *(("activities", old, new) for old, new in new_ids.items())]
    )
    assert _migrations_state(upgrade_db)[13] is False

    notifications = _activity_notifications(upgrade_db)
    assert notifications[1] == {"activity_id": new_ids[1]}
    assert notifications[6] == {"activity_id": new_ids[3], "activity_name": "Ride on second bike"}
    assert str(uuid.UUID(notifications[7]["activity_id"])) == notifications[7]["activity_id"]
    assert notifications[7]["activity_id"] not in new_ids.values()
    assert _rows(upgrade_db, "SELECT id, options::jsonb FROM notifications WHERE type IN (31, 32)") == (
        idp_notifications_before
    )

    by_id = dict(_rows(upgrade_db, "SELECT id::text, activity_ids::jsonb FROM activity_ingestion_jobs"))
    assert len(by_id) == 5
    assert by_id["66666666-6666-4666-8666-666666666666"] == [new_ids[1]]
    assert by_id["66666666-6666-4666-8666-666666666667"] == [new_ids[1], new_ids[3]]
    dangling = by_id["66666666-6666-4666-8666-666666666668"]
    assert dangling[0] == new_ids[3]
    assert str(uuid.UUID(dangling[1])) == dangling[1]
    assert dangling[1] not in new_ids.values()
    assert by_id["66666666-6666-4666-8666-666666666669"] == []
    assert by_id["66666666-6666-4666-8666-666666666670"] is None

    _assert_activity_events_rewritten(upgrade_db, "", new_ids)
    for table, (payload_column, metadata_column) in _JSON_PAYLOAD_COLUMNS.items():
        after = _seeded_rows(upgrade_db, table, payload_column, metadata_column)
        expected = [
            (payload | {"activity_id": new_ids[1]} if row_id.split("-")[2] == "4" else payload, metadata, row_id)
            for payload, metadata, row_id in idp_events_before[table]
        ]
        assert after == expected, table

    alembic_chain.upgrade(upgrade_db, "head")
    assert alembic_chain.schema_differences(upgrade_db) == []
    alembic_chain.bootstrap_substrate(upgrade_db)
    assert alembic_chain.schema_differences(upgrade_db) == []

    with upgrade_db.begin() as connection:
        connection.execute(sa.text("DELETE FROM activities WHERE name = 'Seed ride'"))
    assert {table: _table_count(upgrade_db, table) for table in _ACTIVITY_CHILDREN} == {
        "activity_laps": 1,
        "activity_media": 1,
        "activity_sets": 0,
        "activities_streams": 4,
        "activity_workout_steps": 0,
    }


def test_revision_90_rewrites_the_jasil_prefixed_substrate_tables(upgrade_db):
    _seed_to_87(upgrade_db)
    alembic_chain.upgrade(upgrade_db, _REVISION_89)
    with upgrade_db.begin() as connection:
        for table in _UNPREFIXED_SUBSTRATE_TABLES:
            rows = sa.table(table, sa.column("id"))
            connection.execute(sa.delete(rows).where(rows.c.id.like("act-%")))
    alembic_chain.bootstrap_substrate(upgrade_db)
    assert _scalar(upgrade_db, "SELECT to_regclass('event_outbox')") is None
    _seed(
        upgrade_db,
        lambda connection: alembic_chain.seed_events(
            connection,
            alembic_chain.ACTIVITY_EVENT_CASES,
            alembic_chain.ACTIVITY_EVENT_METADATA,
            alembic_chain.ACTIVITY_EVENT_PREFIX,
            "jasil_",
        ),
    )
    _assert_job_states_covered(upgrade_db, "jasil_", "act")

    alembic_chain.upgrade(upgrade_db, _REVISION_90)

    _assert_activity_events_rewritten(upgrade_db, "jasil_", _new_activity_ids(upgrade_db))
    alembic_chain.upgrade(upgrade_db, "head")
    assert alembic_chain.schema_differences(upgrade_db) == []
    alembic_chain.bootstrap_substrate(upgrade_db)
    assert alembic_chain.schema_differences(upgrade_db) == []


def test_revision_90_is_irreversible(upgrade_db):
    alembic_chain.upgrade(upgrade_db, _REVISION_90)

    with pytest.raises(NotImplementedError):
        alembic_chain.downgrade(upgrade_db, _REVISION_89)

    assert _scalar(upgrade_db, "SELECT version_num FROM alembic_version") == _REVISION_90


def test_migration_13_renames_the_icons_after_the_upgrade(upgrade_db, tmp_path):
    _seed_to_87(upgrade_db)
    old_ids = dict(_rows(upgrade_db, "SELECT slug, id FROM identity_providers"))
    alembic_chain.upgrade(upgrade_db, "head")
    new_ids = _new_ids_by_slug(upgrade_db)
    storage = LocalStorage(str(tmp_path))
    uuid_key = "33333333-3333-4333-8333-333333333333"
    for key, data in (("1", b"one"), ("2", b"two"), ("99", b"orphan"), (uuid_key, b"kept")):
        storage.save("identity_provider_icons", key, data, "image/png")

    def run() -> None:
        with Session(upgrade_db) as db, patch("migrations.migration_13.platform_runtime") as runtime:
            runtime.get_active_platform.return_value.storage = storage
            migration_13.process_migration_13(db)

    run()

    keys = sorted(storage.list_keys("identity_provider_icons", ""))
    assert keys == sorted([new_ids["seed-provider"], new_ids["second-provider"], uuid_key])
    assert storage.get("identity_provider_icons", new_ids[_IDP_PAIRS[1]]) == b"one"
    assert storage.get("identity_provider_icons", new_ids[_IDP_PAIRS[2]]) == b"two"
    assert storage.get("identity_provider_icons", uuid_key) == b"kept"
    assert old_ids == {"seed-provider": 1, "second-provider": 2}
    assert _scalar(upgrade_db, "SELECT to_regclass('uuid_migration_ids')") is None
    assert _migrations_state(upgrade_db)[13] is True

    run()

    assert sorted(storage.list_keys("identity_provider_icons", "")) == keys
    assert _migrations_state(upgrade_db)[13] is True


def test_migration_13_renames_the_activity_files_after_the_upgrade(upgrade_db, tmp_path):
    _seed_to_87(upgrade_db)
    alembic_chain.upgrade(upgrade_db, "head")
    new_ids = _new_activity_ids(upgrade_db)
    storage = LocalStorage(str(tmp_path))
    uuid_key = "33333333-3333-4333-8333-333333333333"
    old_blobs = {
        "activity_files": {
            "processed/1.fit": b"one",
            "processed/3.gpx": b"three",
            "processed/999.tcx": b"orphan",
            f"processed/{uuid_key}.fit": b"kept",
            "upload_staging/0123456789abcdef.fit": b"staged",
        },
        "activity_thumbnails": {
            "1.webp": b"thumb one",
            "3.webp": b"thumb three",
            "999.webp": b"orphan",
            f"{uuid_key}.webp": b"kept",
        },
        "activity_media": {
            "1_aaa.jpg": b"aaa",
            "1_bbb.jpg": b"bbb",
            "1_ccc.jpg": b"ccc",
            "3_ddd.jpg": b"ddd",
            "999_eee.jpg": b"orphan",
            f"{uuid_key}_x.jpg": b"kept",
        },
        "identity_provider_icons": {"1": b"icon"},
    }
    for area, blobs in old_blobs.items():
        for key, data in blobs.items():
            storage.save(area, key, data, "application/octet-stream")

    def run() -> None:
        with Session(upgrade_db) as db, patch("migrations.migration_13.platform_runtime") as runtime:
            runtime.get_active_platform.return_value.storage = storage
            migration_13.process_migration_13(db)

    def listing() -> dict[str, list[str]]:
        return {area: storage.list_keys(area, "") for area in old_blobs}

    run()

    first, third = new_ids[1], new_ids[3]
    expected = {
        "activity_files": {
            f"processed/{first}.fit": b"one",
            f"processed/{third}.gpx": b"three",
            f"processed/{uuid_key}.fit": b"kept",
            "upload_staging/0123456789abcdef.fit": b"staged",
        },
        "activity_thumbnails": {
            f"{first}.webp": b"thumb one",
            f"{third}.webp": b"thumb three",
            f"{uuid_key}.webp": b"kept",
        },
        "activity_media": {
            f"{first}_aaa.jpg": b"aaa",
            f"{first}_bbb.jpg": b"bbb",
            f"{first}_ccc.jpg": b"ccc",
            f"{third}_ddd.jpg": b"ddd",
            f"{uuid_key}_x.jpg": b"kept",
        },
    }
    for area, blobs in expected.items():
        assert storage.list_keys(area, "") == sorted(blobs)
        for key, data in blobs.items():
            assert storage.get(area, key) == data
    assert _rows(
        upgrade_db,
        "SELECT id::text, map_thumbnail_path FROM activities WHERE map_thumbnail_path IS NOT NULL ORDER BY 1",
    ) == sorted([(first, f"{first}.webp"), (third, f"{third}.webp")])
    assert _rows(
        upgrade_db,
        "SELECT activity_id::text, media_path FROM activity_media WHERE media_path <> 'seed/media.jpg' ORDER BY 2",
    ) == sorted(
        [
            (first, f"{first}_aaa.jpg"),
            (first, f"{first}_bbb.jpg"),
            (first, f"{first}_ccc.jpg"),
            (third, f"{third}_ddd.jpg"),
        ],
        key=lambda row: row[1],
    )
    assert _scalar(upgrade_db, "SELECT to_regclass('uuid_migration_ids')") is None
    assert _migrations_state(upgrade_db)[13] is True

    renamed = listing()
    run()

    assert listing() == renamed
