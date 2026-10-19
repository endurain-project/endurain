"""Transaction ownership against a real PostgreSQL database.

``crud`` stages, ``service`` commits and ``get_db`` rolls back. The mock and
SQLite tests show each layer does its part; these show the assumption they all
rest on, which only a database with per-session connections can: staged work is
invisible to everyone else until the owner commits, and a failed flush poisons a
session until somebody rolls it back.
"""

from collections.abc import Generator
from datetime import UTC, datetime
from typing import Annotated
from unittest.mock import MagicMock, patch

import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.exc import PendingRollbackError, SQLAlchemyError
from sqlalchemy.orm import Session

import core.exceptions as core_exceptions
import modules.activities.activity.contracts as activity_contracts
import modules.activities.activity.crud as activity_crud
import modules.activities.activity_laps.crud as laps_crud
import modules.activities.activity_laps.models as laps_models
import modules.activities.activity_media.models as media_models
import modules.activities.activity_media.service as media_service
import modules.followers.crud as followers_crud
import modules.followers.models as followers_models
from tests._helpers.db import ensure_user

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


_LAP = {"start_time": datetime(2026, 7, 28, 9, 0, tzinfo=UTC)}


def _add_activity(factory, user_id: int = 1) -> int:
    """Commit one activity and return its id."""
    ensure_user(factory, user_id)
    core = activity_contracts.ActivityCore(
        user_id=user_id,
        name="Ride",
        distance=1000,
        activity_type=1,
        start_time="2026-07-28T09:00:00",
        end_time="2026-07-28T10:00:00",
        timezone="Europe/Lisbon",
        total_elapsed_time=3600.0,
        total_timer_time=3540.0,
        visibility=2,
        **{flag: False for flag in _PRIVACY_FLAGS},
    )
    with factory() as db:
        created = activity_crud.create_activity(core, db)
        db.commit()
        assert created.id is not None
        return created.id


def _count(factory, model) -> int:
    """Count rows through a fresh session, so only committed rows are visible."""
    with factory() as db:
        return db.scalar(select(func.count()).select_from(model)) or 0


class TestStagedWorkIsPrivateUntilCommit:
    def test_staged_laps_are_invisible_to_other_sessions_until_the_owner_commits(self, pg_factory):
        activity_id = _add_activity(pg_factory)

        owner = pg_factory()
        laps_crud.create_activity_laps([_LAP], activity_id, owner)

        # Flushed, so the owner sees it; nobody else does.
        assert owner.scalar(select(func.count()).select_from(laps_models.ActivityLaps)) == 1
        assert _count(pg_factory, laps_models.ActivityLaps) == 0

        owner.commit()
        assert _count(pg_factory, laps_models.ActivityLaps) == 1
        owner.close()

    def test_a_session_closed_without_committing_loses_the_staged_work(self, pg_factory):
        """The failure the job-state commits exist to prevent."""
        activity_id = _add_activity(pg_factory)

        with pg_factory() as db:
            laps_crud.create_activity_laps([_LAP], activity_id, db)

        assert _count(pg_factory, laps_models.ActivityLaps) == 0


class TestAFailedFlushPoisonsTheSession:
    def _follow_twice(self, db: Session) -> None:
        """Stage the same follow twice, bypassing the pre-check that would 409 first."""
        followers_crud.create_follower(1, 2, db)
        db.commit()
        with patch.object(followers_crud, "get_follower_for_user_id_and_target_user_id", return_value=None):
            followers_crud.create_follower(1, 2, db)

    def test_the_unique_violation_is_a_conflict_and_the_session_needs_a_rollback(self, pg_factory):
        ensure_user(pg_factory, 1)
        ensure_user(pg_factory, 2)

        with pg_factory() as db:
            with pytest.raises(core_exceptions.ConflictError):
                self._follow_twice(db)

            # crud deliberately does not roll back, so until the transaction
            # owner does, the session cannot be used. This is why the media
            # service rolls back before it looks up the winner.
            with pytest.raises(PendingRollbackError):
                db.scalar(select(func.count()).select_from(followers_models.Follower))

            db.rollback()
            assert db.scalar(select(func.count()).select_from(followers_models.Follower)) == 1

    def test_the_committed_row_survives_the_failed_duplicate(self, pg_factory):
        ensure_user(pg_factory, 1)
        ensure_user(pg_factory, 2)

        with pg_factory() as db, pytest.raises(core_exceptions.ConflictError):
            self._follow_twice(db)

        assert _count(pg_factory, followers_models.Follower) == 1


class TestMediaStoreRace:
    def test_the_loser_of_a_content_hash_race_returns_the_winner(self, pg_factory):
        """The unique ``(activity_id, content_hash)`` index decides, not the pre-check.

        The real index raises at flush; ``store_activity_media_bytes`` has to roll
        the poisoned session back before it can read the winner.
        """
        activity_id = _add_activity(pg_factory)
        storage = MagicMock()
        data = b"identical photo bytes"

        with pg_factory() as db:
            winner = media_service.store_activity_media_bytes(activity_id, "photo.jpg", data, storage, db)

        real_lookup = media_service.activity_media_crud.get_activity_media_by_content_hash
        calls = {"n": 0}

        def lookup_after_a_missed_precheck(*args, **kwargs):
            calls["n"] += 1
            # The pre-check races: it sees nothing, then the insert conflicts.
            return None if calls["n"] == 1 else real_lookup(*args, **kwargs)

        with (
            patch.object(
                media_service.activity_media_crud,
                "get_activity_media_by_content_hash",
                side_effect=lookup_after_a_missed_precheck,
            ),
            pg_factory() as db,
        ):
            loser = media_service.store_activity_media_bytes(activity_id, "photo.jpg", data, storage, db)

        assert loser.id == winner.id
        assert _count(pg_factory, media_models.ActivityMedia) == 1


class TestRequestBoundaryRollsBack:
    def test_a_failed_commit_leaves_nothing_behind_and_answers_an_opaque_500(self, pg_factory):
        """The real ``get_db`` plus the real error handler, over a real transaction."""
        import core.database as core_database

        ensure_user(pg_factory, 1)
        ensure_user(pg_factory, 2)
        app = FastAPI()
        core_exceptions.register_exception_handlers(app)

        @app.post("/follow")
        def follow(db: Annotated[Session, Depends(core_database.get_db)]):
            followers_crud.create_follower(1, 2, db)
            raise SQLAlchemyError("commit failed: INSERT ... secret-parameter")

        with patch.object(core_database, "SessionLocal", pg_factory):
            response = TestClient(app, raise_server_exceptions=False).post("/follow")

        assert response.status_code == 500
        assert "secret-parameter" not in response.text
        assert _count(pg_factory, followers_models.Follower) == 0


def test_get_db_is_a_generator_of_sessions():
    """Guards the signature the boundary test above relies on."""
    import core.database as core_database

    assert isinstance(core_database.get_db(), Generator)
