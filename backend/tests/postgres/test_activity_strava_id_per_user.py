"""A Strava activity ID is held per user against real PostgreSQL.

Two Endurain accounts may link the same Strava athlete, so each stores that athlete's activities under the same
Strava activity ID. Only ``(user_id, dedup_key)`` holds an activity once for a user.
"""

import importlib.util
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import patch

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError

import modules.activities.activity.contracts as activity_contracts
import modules.activities.activity.integration_service as activity_integration
import modules.activities.activity.models as activity_models
from tests._helpers.auth import MOCK_USER_ID, OTHER_USER_ID
from tests._helpers.db import ensure_user

_START = datetime(2026, 7, 28, 9, 0, tzinfo=UTC)
_STRAVA_ID = 9_000_000_001
_MIGRATION_PATH = (
    Path(__file__).resolve().parents[2] / "app/alembic/versions/v0_21_0/17_session_digest_and_strava_scope.py"
)
_PRIVACY_FLAGS = (
    "hide_start_time",
    "hide_location",
    "hide_map",
    "hide_hr",
    "hide_power",
    "hide_cadence",
    "hide_elevation",
    "hide_speed",
    "hide_pace",
    "hide_laps",
    "hide_workout_sets_steps",
    "hide_gear",
)


@pytest.fixture
def factory(pg_factory):
    for user_id in (MOCK_USER_ID, OTHER_USER_ID):
        ensure_user(pg_factory, user_id)
    return pg_factory


def _strava_activity(user_id: uuid.UUID) -> activity_contracts.ParsedActivity:
    return activity_contracts.ParsedActivity(
        activity=activity_contracts.ActivityCore(
            user_id=user_id,
            name="Ride",
            distance=1000,
            activity_type=1,
            start_time=_START,
            end_time=_START + timedelta(hours=1),
            total_elapsed_time=3600.0,
            total_timer_time=3540.0,
            strava_activity_id=_STRAVA_ID,
            **{flag: False for flag in _PRIVACY_FLAGS},
        ),
        components={},
        source=activity_contracts.ImportSource(kind="strava"),
    )


def _migration():
    spec = importlib.util.spec_from_file_location("activities_strava_activity_id_per_user", _MIGRATION_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _run(factory, step: str) -> None:
    migration = _migration()
    with factory() as db:
        with (
            patch.object(migration.op, "execute", side_effect=lambda sql: db.execute(text(sql))),
            patch.object(migration.op, "get_bind", return_value=db.connection()),
            patch.object(
                migration.op,
                "drop_constraint",
                side_effect=lambda name, table, type_: db.execute(
                    text(f'ALTER TABLE {table} DROP CONSTRAINT "{name}"')
                ),
            ),
            patch.object(
                migration.op,
                "create_unique_constraint",
                side_effect=lambda name, table, columns: db.execute(
                    text(f'ALTER TABLE {table} ADD CONSTRAINT "{name}" UNIQUE ({", ".join(columns)})')
                ),
            ),
            patch.object(
                migration.op,
                "create_index",
                side_effect=lambda name, table, columns: db.execute(
                    text(f'CREATE INDEX "{name}" ON {table} ({", ".join(columns)})')
                ),
            ),
            patch.object(
                migration.op,
                "drop_index",
                side_effect=lambda name, table_name: db.execute(text(f'DROP INDEX "{name}"')),
            ),
        ):
            getattr(migration, f"{step}_activities_strava_activity_id_per_user")()
        db.commit()


def _insert_activity(db, user_id: uuid.UUID, strava_id: int, dedup_key: str) -> uuid.UUID:
    activity = activity_models.Activity(
        user_id=user_id,
        distance=1,
        activity_type=1,
        start_time=_START,
        end_time=_START + timedelta(hours=1),
        total_elapsed_time=1,
        total_timer_time=1,
        strava_activity_id=strava_id,
        dedup_key=dedup_key,
        visibility=0,
        created_at=_START,
        **{flag: False for flag in _PRIVACY_FLAGS},
    )
    db.add(activity)
    db.flush()
    return activity.id


def test_two_users_store_the_same_strava_activity(factory):
    with factory() as db:
        first = activity_integration.store_parsed_activity(_strava_activity(MOCK_USER_ID), db)
        second = activity_integration.store_parsed_activity(_strava_activity(OTHER_USER_ID), db)
        db.commit()

    assert first.id != second.id
    with factory() as db:
        owners = db.scalars(
            select(activity_models.Activity.user_id).where(activity_models.Activity.strava_activity_id == _STRAVA_ID)
        ).all()
    assert sorted(owners) == sorted([MOCK_USER_ID, OTHER_USER_ID])


def test_the_downgrade_keeps_one_holder_and_the_upgrade_lets_users_share_again(factory):
    _run(factory, "downgrade")
    with factory() as db:
        kept = _insert_activity(db, MOCK_USER_ID, _STRAVA_ID, f"strava:{_STRAVA_ID}")
        db.commit()
    with factory() as db, pytest.raises(IntegrityError):
        _insert_activity(db, OTHER_USER_ID, _STRAVA_ID, f"strava:{_STRAVA_ID}")

    _run(factory, "upgrade")
    with factory() as db:
        _insert_activity(db, OTHER_USER_ID, _STRAVA_ID, f"strava:{_STRAVA_ID}")
        db.commit()
        holders = db.execute(text("SELECT id FROM activities WHERE strava_activity_id = :id"), {"id": _STRAVA_ID}).all()
    assert len(holders) == 2
    assert kept in {row.id for row in holders}

    _run(factory, "downgrade")
    with factory() as db:
        remaining = db.execute(text("SELECT id FROM activities WHERE strava_activity_id IS NOT NULL")).all()
    assert [row.id for row in remaining] == [min(row.id for row in holders)]
