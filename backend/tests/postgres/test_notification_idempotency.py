"""A redelivered event creates its notification once, even when deliveries overlap."""

import threading
import uuid

from sqlalchemy import func, select

import modules.notifications.constants as notifications_constants
import modules.notifications.crud as notifications_crud
import modules.notifications.models as notifications_models
import modules.notifications.schema as notifications_schema
from tests._helpers.db import ensure_user


def test_concurrent_deliveries_of_one_event_create_one_notification(pg_factory):
    ensure_user(pg_factory, 1)
    event_id = str(uuid.uuid4())
    barrier = threading.Barrier(6)
    created: list[bool] = []

    def deliver() -> None:
        barrier.wait()
        with pg_factory() as db:
            _, was_created = notifications_crud.create_notification_once(
                notifications_schema.NotificationCreate(
                    user_id=1,
                    type=notifications_constants.NotificationType.NEW_ACTIVITY,
                    source_event_id=event_id,
                    options={"activity_id": 7},
                ),
                db,
            )
            created.append(was_created)

    threads = [threading.Thread(target=deliver) for _ in range(6)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=20)

    assert created.count(True) == 1
    assert len(created) == 6
    with pg_factory() as db:
        assert db.scalar(select(func.count()).select_from(notifications_models.Notification)) == 1
