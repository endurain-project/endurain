"""The scheduled retention job opens its own session and commits what it purges."""

import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import select, update

import modules.notifications.constants as notifications_constants
import modules.notifications.models as notifications_models
import modules.notifications.scheduled_jobs as notifications_scheduled_jobs
import modules.server_settings.models as server_settings_models
from tests._factories.notifications import make_notification_of
from tests._factories.users import make_user


def test_the_job_purges_the_read_notifications_past_the_retention(committed_sessions):
    now = datetime.now(UTC)
    with committed_sessions() as db:
        user = make_user(db)
        db.execute(update(server_settings_models.ServerSettings).values(read_notification_retention_days=30))

        def make(**kwargs):
            return make_notification_of(
                db,
                user.id,
                notifications_constants.NotificationType.NEW_ACTIVITY,
                {"activity_id": str(uuid.uuid4())},
                **kwargs,
            )

        make(read=True, created_at=now - timedelta(days=31))
        kept = make(read=True, created_at=now - timedelta(days=29))
        db.commit()

    notifications_scheduled_jobs.delete_read_notifications()

    with committed_sessions() as db:
        assert list(db.scalars(select(notifications_models.Notification.id))) == [kept.id]
