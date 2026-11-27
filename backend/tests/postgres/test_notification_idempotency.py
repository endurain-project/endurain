"""A redelivered event creates its notification once, even when deliveries overlap."""

import threading
import uuid

from sqlalchemy import func, select

import modules.notifications.constants as notifications_constants
import modules.notifications.crud as notifications_crud
import modules.notifications.models as notifications_models
import modules.notifications.schema as notifications_schema
from tests._helpers.db import ensure_user

_ID_1 = uuid.uuid4()
_ID_2 = uuid.uuid4()
_ID_3 = uuid.uuid4()


def test_concurrent_deliveries_of_one_event_create_one_notification(pg_factory):
    ensure_user(pg_factory, _ID_1)
    event_id = str(uuid.uuid4())
    barrier = threading.Barrier(6)
    created: list[bool] = []

    def deliver() -> None:
        barrier.wait()
        with pg_factory() as db:
            _, was_created = notifications_crud.create_notification_once(
                notifications_schema.NotificationCreate(
                    user_id=_ID_1,
                    type=notifications_constants.NotificationType.NEW_ACTIVITY,
                    source_event_id=event_id,
                    options={"activity_id": str(uuid.uuid4())},
                ),
                db,
            )
            db.commit()
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


def test_deleting_notifications_naming_a_user_matches_the_json_reference(pg_factory):
    for user_id in (_ID_1, _ID_2, _ID_3):
        ensure_user(pg_factory, user_id)
    with pg_factory() as db:
        for owner, options in [
            (_ID_1, {"user_id": str(_ID_3), "user_name": "A", "user_username": "a"}),
            (_ID_2, {"user_id": str(_ID_3), "user_name": "A", "user_username": "a"}),
            (_ID_1, {"user_id": str(_ID_2), "user_name": "B", "user_username": "b"}),
            (_ID_2, {"user_id": str(_ID_1), "user_name": "C", "user_username": "c"}),
        ]:
            notifications_crud.create_notification(
                notifications_schema.NotificationCreate(
                    user_id=owner, type=notifications_constants.NotificationType.NEW_FOLLOWER_REQUEST, options=options
                ),
                db,
            )
        db.commit()

    with pg_factory() as db:
        assert notifications_crud.delete_notifications_naming_user(_ID_3, db) == 2
        db.commit()
        assert db.scalar(select(func.count()).select_from(notifications_models.Notification)) == 2
