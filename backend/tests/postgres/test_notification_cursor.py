"""The notification list is a keyset feed: a notification created between two slices shifts nothing."""

from sqlalchemy import update

import modules.notifications.constants as notifications_constants
import modules.notifications.crud as notifications_crud
import modules.notifications.models as notifications_models
import modules.notifications.schema as notifications_schema
import modules.notifications.service as notifications_service
from tests._helpers.db import ensure_user


def _create(pg_factory, count: int) -> list[int]:
    with pg_factory() as db:
        ids = [
            notifications_crud.create_notification(
                notifications_schema.NotificationCreate(
                    user_id=1,
                    type=notifications_constants.NotificationType.NEW_ACTIVITY,
                    options={"activity_id": n},
                ),
                db,
            ).id
            for n in range(count)
        ]
        db.commit()
    return ids


def _walk(pg_factory, num_records: int, *, unread_only: bool = False) -> list[int]:
    seen: list[int] = []
    cursor = None
    while True:
        with pg_factory() as db:
            page = notifications_service.list_notifications(
                1, db, cursor=cursor, num_records=num_records, unread_only=unread_only
            )
        seen.extend(item.id for item in page.items)
        cursor = page.next_cursor
        if cursor is None:
            return seen


def test_a_notification_created_between_slices_does_not_shift_or_repeat_rows(pg_factory):
    ensure_user(pg_factory, 1)
    ids = _create(pg_factory, 5)
    with pg_factory() as db:
        first = notifications_service.list_notifications(1, db, cursor=None, num_records=2)
    assert [n.id for n in first.items] == ids[::-1][:2]

    newcomer = _create(pg_factory, 1)[0]

    with pg_factory() as db:
        second = notifications_service.list_notifications(1, db, cursor=first.next_cursor, num_records=2)
        third = notifications_service.list_notifications(1, db, cursor=second.next_cursor, num_records=2)
    resumed = [n.id for n in second.items] + [n.id for n in third.items]
    assert resumed == ids[::-1][2:]
    assert newcomer not in resumed
    assert third.next_cursor is None


def test_unread_only_pages_over_the_unread_rows_with_the_cursor(pg_factory):
    ensure_user(pg_factory, 1)
    ids = _create(pg_factory, 6)
    read_ids = {ids[1], ids[4]}
    with pg_factory() as db:
        db.execute(
            update(notifications_models.Notification)
            .where(notifications_models.Notification.id.in_(read_ids))
            .values(read=True)
        )
        db.commit()

    seen = _walk(pg_factory, 2, unread_only=True)

    assert seen == [i for i in ids[::-1] if i not in read_ids]
