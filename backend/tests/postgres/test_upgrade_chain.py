"""The real Alembic chain, run against an empty database and against a seeded v0.20.x install."""

import json
import uuid
from collections import Counter
from datetime import timedelta
from unittest.mock import patch

import pytest
import sqlalchemy as sa
from jasil.backends.storage_local import LocalStorage
from sqlalchemy.orm import Session

import migrations.migration_13 as migration_13
from tests._helpers import alembic_chain

_REVISION_0 = "c5cfe02a11c2"
_REVISION_84 = "b84e9f3a6c25"
_REVISION_85 = "b41c0afdc9d9"
_REVISION_86 = "3e7a91d4c0b8"
_REVISION_87 = "e05703e64861"
_REVISION_88 = "dc5f0450aaf0"
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
    assert after == {**before, "migrations": before["migrations"] - 9 + 1, _TABLE_EMPTIED_BY_REVISION_87: 0}
    assert set(_migrations_state(upgrade_db)) == {7, 11, 12, 13}
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

    alembic_chain.upgrade(upgrade_db, "head")

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


def _seeded_rows(engine, table: str, *columns: str) -> list[tuple]:
    """Return the given columns of the rows the identity-provider seeds added to a substrate table, by id."""
    rows = sa.table(table, sa.column("id"), *(sa.column(name) for name in columns))
    statement = (
        sa.select(*(rows.c[name] for name in columns), rows.c.id).where(rows.c.id.like("idp-%")).order_by(rows.c.id)
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


def _assert_job_states_covered(engine, prefix: str) -> None:
    jobs = _seeded_rows(engine, f"{prefix}processing_jobs", "status", "attempts")
    assert {(status, attempts > 0) for status, attempts, _ in jobs} == {
        ("claimed", False),
        ("completed", False),
        ("dead_letter", False),
        ("pending", False),
        ("pending", True),
    }
    relayed = _seeded_rows(engine, f"{prefix}event_outbox", "relayed_at")
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

    alembic_chain.upgrade(upgrade_db, "head")

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
        "SELECT options::jsonb FROM notifications WHERE id IN (SELECT id FROM notifications WHERE user_id = 1 AND type = 1)",
    ) == [({"activity_id": 1},)]

    assert sorted(_rows(upgrade_db, "SELECT table_name, old_id, new_id::text FROM uuid_migration_ids")) == sorted(
        ("identity_providers", old_ids[slug], new_ids[slug]) for slug in old_ids
    )
    assert _migrations_state(upgrade_db)[13] is False
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
    _seed(upgrade_db, lambda connection: alembic_chain.seed_idp_events(connection, "jasil_"))
    _assert_job_states_covered(upgrade_db, "jasil_")

    alembic_chain.upgrade(upgrade_db, "head")

    _assert_events_rewritten(upgrade_db, "jasil_", _new_ids_by_slug(upgrade_db))
    assert alembic_chain.schema_differences(upgrade_db) == []
    alembic_chain.bootstrap_substrate(upgrade_db)
    assert alembic_chain.schema_differences(upgrade_db) == []


def test_revision_88_is_irreversible(upgrade_db):
    alembic_chain.upgrade(upgrade_db, "head")

    with pytest.raises(NotImplementedError):
        alembic_chain.downgrade(upgrade_db, _REVISION_87)

    assert _scalar(upgrade_db, "SELECT version_num FROM alembic_version") == _REVISION_88


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
