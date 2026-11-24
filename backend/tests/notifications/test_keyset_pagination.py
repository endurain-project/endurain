"""The notification list is a keyset feed: a notification created between two slices shifts nothing."""

import uuid

import pytest
from sqlalchemy import update

import core.pagination as core_pagination
import modules.notifications.constants as notifications_constants
import modules.notifications.models as notifications_models
import modules.notifications.service as notifications_service
from tests._factories.notifications import make_notification_of
from tests._factories.users import make_user

_NEW_ACTIVITY = notifications_constants.NotificationType.NEW_ACTIVITY


@pytest.fixture
def user_id(committed_sessions) -> uuid.UUID:
    with committed_sessions() as db:
        user = make_user(db)
        db.commit()
    return user.id


def _create(committed_sessions, user_id: uuid.UUID, count: int) -> list[uuid.UUID]:
    """Create ``count`` notifications, each in its own transaction so ``created_at`` strictly increases."""
    ids: list[uuid.UUID] = []
    for _ in range(count):
        with committed_sessions() as db:
            ids.append(make_notification_of(db, user_id, _NEW_ACTIVITY, {"activity_id": str(uuid.uuid4())}).id)
            db.commit()
    return ids


def _walk(committed_sessions, user_id: uuid.UUID, num_records: int, *, unread_only: bool = False) -> list[uuid.UUID]:
    seen: list[uuid.UUID] = []
    cursor = None
    while True:
        with committed_sessions() as db:
            page = notifications_service.list_notifications(
                user_id, db, cursor=cursor, num_records=num_records, unread_only=unread_only
            )
        seen.extend(item.id for item in page.items)
        cursor = page.next_cursor
        if cursor is None:
            return seen


def test_a_notification_created_between_slices_does_not_shift_or_repeat_rows(committed_sessions, user_id):
    ids = _create(committed_sessions, user_id, 5)
    with committed_sessions() as db:
        first = notifications_service.list_notifications(user_id, db, cursor=None, num_records=2)
    assert [n.id for n in first.items] == ids[::-1][:2]

    newcomer = _create(committed_sessions, user_id, 1)[0]

    with committed_sessions() as db:
        second = notifications_service.list_notifications(user_id, db, cursor=first.next_cursor, num_records=2)
        third = notifications_service.list_notifications(user_id, db, cursor=second.next_cursor, num_records=2)
    resumed = [n.id for n in second.items] + [n.id for n in third.items]
    assert resumed == ids[::-1][2:]
    assert newcomer not in resumed
    assert third.next_cursor is None


def test_unread_only_pages_over_the_unread_rows_with_the_cursor(committed_sessions, user_id):
    ids = _create(committed_sessions, user_id, 6)
    read_ids = {ids[1], ids[4]}
    with committed_sessions() as db:
        db.execute(
            update(notifications_models.Notification)
            .where(notifications_models.Notification.id.in_(read_ids))
            .values(read=True)
        )
        db.commit()

    seen = _walk(committed_sessions, user_id, 2, unread_only=True)

    assert seen == [i for i in ids[::-1] if i not in read_ids]


def test_the_cursor_round_trips_a_notification_uuid(committed_sessions, user_id):
    ids = _create(committed_sessions, user_id, 3)
    with committed_sessions() as db:
        first = notifications_service.list_notifications(user_id, db, cursor=None, num_records=1)
    assert first.next_cursor is not None
    assert core_pagination.decode_uuid_cursor(first.next_cursor)[1] == ids[-1]
