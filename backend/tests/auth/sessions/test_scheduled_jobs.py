"""The scheduled cleanup ends expired and idle sessions in a session of its own and keeps the live ones."""

from datetime import UTC, datetime, timedelta

import sqlalchemy as sa

import modules.auth.sessions.models as sessions_models
import modules.auth.sessions.scheduled_jobs as sessions_scheduled_jobs
from tests._factories.auth import make_session
from tests._factories.server_settings import edit_server_settings
from tests._factories.users import make_user


def test_the_job_deletes_expired_and_idle_sessions_and_keeps_the_live_ones(committed_sessions):
    with committed_sessions() as db:
        edit_server_settings(
            db, session_idle_timeout_enabled=True, session_idle_timeout_hours=1, access_token_expire_minutes=15
        )
        user = make_user(db)
        live = make_session(db, user)
        make_session(db, user, expires_at=datetime.now(UTC) - timedelta(minutes=1))
        make_session(db, user, last_activity_at=datetime.now(UTC) - timedelta(hours=2))
        db.commit()

    sessions_scheduled_jobs.delete_stale_sessions()

    with committed_sessions() as db:
        assert set(db.scalars(sa.select(sessions_models.UsersSessions.id))) == {live.id}
