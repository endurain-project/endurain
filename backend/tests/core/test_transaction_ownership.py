"""Transaction ownership against a real PostgreSQL database.

``crud`` stages, ``service`` commits and ``get_db`` rolls back. These show the assumption every layer rests on, which
only a database with per-session connections can: staged work is invisible to everyone else until the owner commits,
and a failed flush poisons a session until somebody rolls it back.
"""

import uuid
from datetime import UTC, datetime
from typing import Annotated

import jasil.runtime as platform_runtime
import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.exc import PendingRollbackError, SQLAlchemyError
from sqlalchemy.orm import Session

import core.database as core_database
import core.exceptions as core_exceptions
import modules.activities.activity_laps.crud as laps_crud
import modules.activities.activity_laps.models as laps_models
import modules.activities.activity_media.models as media_models
import modules.activities.activity_media.service as media_service
import modules.followers.crud as followers_crud
import modules.followers.models as followers_models
from tests._factories.activities import make_activity
from tests._factories.users import make_user
from tests._helpers import images

_LAP = {"start_time": datetime(2026, 7, 28, 9, 0, tzinfo=UTC)}


def _count(factory, model) -> int:
    """Count rows through a fresh session, so only committed rows are visible."""
    with factory() as db:
        return db.scalar(select(func.count()).select_from(model)) or 0


def _blind_session(factory) -> Session:
    """Open a session whose snapshot is taken now, so it cannot see what other sessions commit afterwards."""
    db = factory()
    db.connection(execution_options={"isolation_level": "REPEATABLE READ"})
    db.execute(select(1))
    return db


@pytest.fixture
def activity_id(committed_sessions) -> uuid.UUID:
    with committed_sessions() as db:
        created = make_activity(db, make_user(db).id)
        db.commit()
    return created.id


@pytest.fixture
def two_users(committed_sessions) -> tuple[uuid.UUID, uuid.UUID]:
    with committed_sessions() as db:
        first, second = make_user(db).id, make_user(db).id
        db.commit()
    return first, second


class TestStagedWorkIsPrivateUntilCommit:
    def test_staged_laps_are_invisible_to_other_sessions_until_the_owner_commits(self, committed_sessions, activity_id):
        owner = committed_sessions()
        laps_crud.create_activity_laps([_LAP], activity_id, owner)

        # Flushed, so the owner sees it; nobody else does.
        assert owner.scalar(select(func.count()).select_from(laps_models.ActivityLaps)) == 1
        assert _count(committed_sessions, laps_models.ActivityLaps) == 0

        owner.commit()
        assert _count(committed_sessions, laps_models.ActivityLaps) == 1
        owner.close()

    def test_a_session_closed_without_committing_loses_the_staged_work(self, committed_sessions, activity_id):
        """The failure the job-state commits exist to prevent."""
        with committed_sessions() as db:
            laps_crud.create_activity_laps([_LAP], activity_id, db)

        assert _count(committed_sessions, laps_models.ActivityLaps) == 0


class TestAFailedFlushPoisonsTheSession:
    def test_the_unique_violation_is_a_conflict_and_the_session_needs_a_rollback(self, committed_sessions, two_users):
        db = _blind_session(committed_sessions)
        with committed_sessions() as first:
            followers_crud.create_follower(*two_users, first)
            first.commit()

        with pytest.raises(core_exceptions.ConflictError):
            followers_crud.create_follower(*two_users, db)

        # crud deliberately does not roll back, so until the transaction owner does, the session cannot be used.
        # This is why the media service rolls back before it looks up the winner.
        with pytest.raises(PendingRollbackError):
            db.scalar(select(func.count()).select_from(followers_models.Follower))

        db.rollback()
        assert db.scalar(select(func.count()).select_from(followers_models.Follower)) == 1
        db.close()

    def test_the_committed_row_survives_the_failed_duplicate(self, committed_sessions, two_users):
        blind = _blind_session(committed_sessions)
        with committed_sessions() as first:
            followers_crud.create_follower(*two_users, first)
            first.commit()

        with blind, pytest.raises(core_exceptions.ConflictError):
            followers_crud.create_follower(*two_users, blind)

        assert _count(committed_sessions, followers_models.Follower) == 1


class TestMediaStoreRace:
    def test_the_loser_of_a_content_hash_race_returns_the_winner(self, committed_sessions, activity_id):
        """The unique ``(activity_id, content_hash)`` index decides, not the pre-check.

        The loser's snapshot predates the winner's commit, so its pre-check finds nothing and the real index raises
        at flush; ``store_activity_media_bytes`` has to roll the poisoned session back before it can read the winner.
        """
        storage = platform_runtime.get_active_platform().storage
        data = images.jpeg_with_exif()
        loser_session = _blind_session(committed_sessions)

        with committed_sessions() as db:
            winner = media_service.store_activity_media_bytes(activity_id, "photo.jpg", data, storage, db)

        with loser_session as db:
            loser = media_service.store_activity_media_bytes(activity_id, "photo.jpg", data, storage, db)

        assert loser.id == winner.id
        assert _count(committed_sessions, media_models.ActivityMedia) == 1


class TestRequestBoundaryRollsBack:
    def test_a_failed_commit_leaves_nothing_behind_and_answers_an_opaque_500(self, committed_sessions, two_users):
        """The real ``get_db`` plus the real error handler, over a real transaction."""
        follower, followee = two_users
        app = FastAPI()
        core_exceptions.register_exception_handlers(app)

        @app.post("/follow")
        def follow(db: Annotated[Session, Depends(core_database.get_db)]):
            followers_crud.create_follower(follower, followee, db)
            raise SQLAlchemyError("commit failed: INSERT ... secret-parameter")

        response = TestClient(app, raise_server_exceptions=False).post("/follow")

        assert response.status_code == 500
        assert "secret-parameter" not in response.text
        assert _count(committed_sessions, followers_models.Follower) == 0
