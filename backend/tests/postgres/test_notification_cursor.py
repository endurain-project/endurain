"""The notification list is a keyset feed: a notification created between two slices shifts nothing."""

import uuid

from sqlalchemy import update

import core.pagination as core_pagination
import modules.notifications.constants as notifications_constants
import modules.notifications.crud as notifications_crud
import modules.notifications.models as notifications_models
import modules.notifications.schema as notifications_schema
import modules.notifications.service as notifications_service
from tests._helpers.db import ensure_user

_ID_1 = uuid.uuid4()


def _create(pg_factory, count: int) -> list[uuid.UUID]:
    """Create ``count`` notifications, each in its own transaction so ``created_at`` strictly increases."""
    ids: list[uuid.UUID] = []
    for _ in range(count):
        with pg_factory() as db:
            ids.append(
                notifications_crud.create_notification(
                    notifications_schema.NotificationCreate(
                        user_id=_ID_1,
                        type=notifications_constants.NotificationType.NEW_ACTIVITY,
                        options={"activity_id": str(uuid.uuid4())},
                    ),
                    db,
                ).id
            )
            db.commit()
    return ids


def _walk(pg_factory, num_records: int, *, unread_only: bool = False) -> list[uuid.UUID]:
    seen: list[uuid.UUID] = []
    cursor = None
    while True:
        with pg_factory() as db:
            page = notifications_service.list_notifications(
                _ID_1, db, cursor=cursor, num_records=num_records, unread_only=unread_only
            )
        seen.extend(item.id for item in page.items)
        cursor = page.next_cursor
        if cursor is None:
            return seen


def test_a_notification_created_between_slices_does_not_shift_or_repeat_rows(pg_factory):
    ensure_user(pg_factory, _ID_1)
    ids = _create(pg_factory, 5)
    with pg_factory() as db:
        first = notifications_service.list_notifications(_ID_1, db, cursor=None, num_records=2)
    assert [n.id for n in first.items] == ids[::-1][:2]

    newcomer = _create(pg_factory, 1)[0]

    with pg_factory() as db:
        second = notifications_service.list_notifications(_ID_1, db, cursor=first.next_cursor, num_records=2)
        third = notifications_service.list_notifications(_ID_1, db, cursor=second.next_cursor, num_records=2)
    resumed = [n.id for n in second.items] + [n.id for n in third.items]
    assert resumed == ids[::-1][2:]
    assert newcomer not in resumed
    assert third.next_cursor is None


def test_unread_only_pages_over_the_unread_rows_with_the_cursor(pg_factory):
    ensure_user(pg_factory, _ID_1)
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


def test_the_cursor_round_trips_a_notification_uuid(pg_factory):
    ensure_user(pg_factory, _ID_1)
    ids = _create(pg_factory, 3)
    with pg_factory() as db:
        first = notifications_service.list_notifications(_ID_1, db, cursor=None, num_records=1)
    assert first.next_cursor is not None
    assert core_pagination.decode_uuid_cursor(first.next_cursor)[1] == ids[-1]
