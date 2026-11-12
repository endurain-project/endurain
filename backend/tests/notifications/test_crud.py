import uuid
from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy.exc import IntegrityError

import core.exceptions as core_exceptions
from tests._helpers.db import create_sqlite_session


def _nid(number: int) -> uuid.UUID:
    """Return a notification ID that sorts by ``number``."""
    return uuid.UUID(int=number)


class TestGetUserNotificationById:
    def test_success(self, mock_db):
        import modules.notifications.crud as crud
        import modules.notifications.models as m

        n = MagicMock(
            spec=m.Notification,
            id=_nid(1),
            user_id=1,
            type=1,
            read=False,
            options={"activity_id": "11111111-1111-4111-8111-111111111111"},
            created_at=datetime(2024, 1, 1),
        )
        mock_db.execute.return_value.scalars.return_value.first.return_value = n
        r = crud.get_user_notification_by_id(notification_id=_nid(1), user_id=1, db=mock_db)
        assert r is not None
        assert r.id == _nid(1)
        assert r.user_id == 1

    def test_not_found(self, mock_db):
        import modules.notifications.crud as crud

        mock_db.execute.return_value.scalars.return_value.first.return_value = None
        r = crud.get_user_notification_by_id(notification_id=_nid(999), user_id=1, db=mock_db)
        assert r is None


class TestGetUserNotificationsCount:
    def test_success(self, mock_db):
        import modules.notifications.crud as crud

        mock_db.execute.return_value.scalar_one.return_value = 7
        r = crud.count_user_unread_notifications(user_id=1, db=mock_db)
        assert r == 7

    def test_zero(self, mock_db):
        import modules.notifications.crud as crud

        mock_db.execute.return_value.scalar_one.return_value = 0
        r = crud.count_user_unread_notifications(user_id=1, db=mock_db)
        assert r == 0


class TestGetUserNotificationsAfter:
    def test_success(self, mock_db):
        import modules.notifications.crud as crud
        import modules.notifications.models as m

        n = MagicMock(
            spec=m.Notification,
            id=_nid(1),
            user_id=1,
            type=1,
            read=False,
            options={"activity_id": "11111111-1111-4111-8111-111111111111"},
            created_at=datetime(2024, 1, 1),
        )
        mock_db.execute.return_value.scalars.return_value.all.return_value = [n]
        r = crud.get_user_notifications_after(1, None, 5, mock_db)
        assert len(r) == 1
        assert r[0].id == _nid(1)
        assert r[0].user_id == 1

    def test_empty(self, mock_db):
        import modules.notifications.crud as crud

        mock_db.execute.return_value.scalars.return_value.all.return_value = []
        assert crud.get_user_notifications_after(1, None, 5, mock_db) == []


class TestUnreadOnlyFilter:
    """The unread filter is a SQL ``WHERE``, so it runs against a real session."""

    @pytest.fixture
    def db(self):
        import modules.notifications.models as m

        session = create_sqlite_session()
        # User 1: two read and three unread, oldest first. User 2: one unread.
        for notification_id, user_id, read in [
            (1, 1, True),
            (2, 1, False),
            (3, 1, True),
            (4, 1, False),
            (5, 1, False),
            (6, 2, False),
        ]:
            session.add(
                m.Notification(
                    id=_nid(notification_id),
                    user_id=user_id,
                    type=1,
                    read=read,
                    options={"activity_id": str(_nid(notification_id))},
                    created_at=datetime(2024, 1, notification_id),
                )
            )
        session.commit()
        yield session
        session.close()

    def test_count_unread_only_skips_read_and_other_users_notifications(self, db):
        import modules.notifications.crud as crud

        assert crud.count_user_unread_notifications(user_id=1, db=db) == 3

    def test_count_unread_only_is_zero_once_everything_is_read(self, db):
        import modules.notifications.crud as crud

        crud.mark_all_notifications_as_read(1, db)

        assert crud.count_user_unread_notifications(user_id=1, db=db) == 0

    def test_slice_unread_only_returns_the_unread_ones_newest_first(self, db):
        import modules.notifications.crud as crud

        page = crud.get_user_notifications_after(1, None, 10, db, unread_only=True)

        assert [n.id for n in page] == [_nid(5), _nid(4), _nid(2)]
        assert all(not n.read for n in page)

    def test_slice_resumes_strictly_after_the_position(self, db):
        import modules.notifications.crud as crud

        second = crud.get_user_notifications_after(1, (datetime(2024, 1, 4), _nid(4)), 2, db, unread_only=True)

        assert [n.id for n in second] == [_nid(2)]

    def test_slice_includes_read_notifications_by_default(self, db):
        import modules.notifications.crud as crud

        page = crud.get_user_notifications_after(1, None, 10, db)

        assert [n.id for n in page] == [_nid(n) for n in (5, 4, 3, 2, 1)]

    def test_slice_breaks_a_created_at_tie_on_id(self, db):
        import modules.notifications.crud as crud
        import modules.notifications.models as m

        for notification_id in (7, 8):
            db.add(
                m.Notification(
                    id=_nid(notification_id),
                    user_id=1,
                    type=1,
                    read=False,
                    options={"activity_id": "11111111-1111-4111-8111-111111111111"},
                    created_at=datetime(2024, 1, 5),
                )
            )
        db.commit()

        first = crud.get_user_notifications_after(1, None, 2, db)
        rest = crud.get_user_notifications_after(1, (datetime(2024, 1, 5), first[-1].id), 10, db)

        assert [n.id for n in first] == [_nid(8), _nid(7)]
        assert [n.id for n in rest] == [_nid(n) for n in (5, 4, 3, 2, 1)]


class TestCreateNotification:
    def test_success(self, mock_db):
        import modules.notifications.crud as crud
        import modules.notifications.schema as schema

        notification_data = schema.NotificationCreate(
            user_id=1, type="new_activity", options={"activity_id": "11111111-1111-4111-8111-111111111111"}
        )

        mock_notification = MagicMock()
        mock_notification.id = _nid(1)
        mock_notification.user_id = 1
        mock_notification.type = 1
        mock_notification.read = False
        mock_notification.options = {"activity_id": "11111111-1111-4111-8111-111111111111"}
        mock_notification.created_at = datetime(2024, 1, 1)

        with patch("modules.notifications.crud.notifications_models.Notification", return_value=mock_notification):
            n = crud.create_notification(notification=notification_data, db=mock_db)
        assert n is not None
        mock_db.add.assert_called_once()
        mock_db.flush.assert_called_once()
        mock_db.refresh.assert_called_once()


class TestCreateNotificationOnce:
    def test_replay_returns_existing_notification(self, mock_db):
        import modules.notifications.crud as crud
        import modules.notifications.schema as schema

        notification_data = schema.NotificationCreate(
            user_id=2,
            type="new_follower_request",
            source_event_id="event-1",
            options={"user_id": 1},
        )
        existing = MagicMock(id=7)

        with (
            patch("modules.notifications.crud.get_notification_by_source_event", return_value=existing),
            patch("modules.notifications.crud.create_notification") as create_notification,
        ):
            notification, created = crud.create_notification_once(notification_data, mock_db)

        assert notification is existing
        assert created is False
        create_notification.assert_not_called()

    def test_concurrent_duplicate_returns_winning_notification(self, mock_db):
        import modules.notifications.crud as crud
        import modules.notifications.schema as schema

        notification_data = schema.NotificationCreate(
            user_id=2,
            type="new_follower_request",
            source_event_id="event-1",
            options={"user_id": 1},
        )
        existing = MagicMock(id=7)
        integrity_error = IntegrityError("INSERT", {}, RuntimeError("duplicate"))
        mock_db.begin_nested.return_value.__exit__.return_value = False

        with (
            patch(
                "modules.notifications.crud.get_notification_by_source_event",
                side_effect=[None, existing],
            ),
            patch(
                "modules.notifications.crud.create_notification",
                side_effect=integrity_error,
            ),
        ):
            notification, created = crud.create_notification_once(notification_data, mock_db)

        assert notification is existing
        assert created is False

    def test_unrelated_integrity_error_becomes_conflict(self, mock_db):
        import modules.notifications.crud as crud
        import modules.notifications.schema as schema

        notification_data = schema.NotificationCreate(
            user_id=2,
            type="new_follower_request",
            source_event_id="event-1",
            options={"user_id": 1},
        )
        integrity_error = IntegrityError("INSERT", {}, RuntimeError("foreign key"))
        mock_db.begin_nested.return_value.__exit__.return_value = False

        with (
            patch(
                "modules.notifications.crud.get_notification_by_source_event",
                return_value=None,
            ),
            patch(
                "modules.notifications.crud.create_notification",
                side_effect=integrity_error,
            ),
            pytest.raises(core_exceptions.ConflictError),
        ):
            crud.create_notification_once(notification_data, mock_db)


class TestMarkNotificationAsRead:
    def test_success(self, mock_db):
        import modules.notifications.crud as crud
        import modules.notifications.models as m

        n = MagicMock(
            spec=m.Notification,
            id=_nid(1),
            user_id=1,
            type=1,
            read=False,
            options={"activity_id": "11111111-1111-4111-8111-111111111111"},
            created_at=datetime(2024, 1, 1),
        )
        mock_db.execute.return_value.scalars.return_value.first.return_value = n

        r = crud.mark_notification_as_read(notification_id=_nid(1), user_id=1, db=mock_db)
        assert n.read is True
        assert r is not None
        assert r.id == _nid(1)
        assert r.user_id == 1
        mock_db.flush.assert_called_once()
        mock_db.refresh.assert_called_once_with(n)

    def test_not_found(self, mock_db):
        import modules.notifications.crud as crud

        mock_db.execute.return_value.scalars.return_value.first.return_value = None
        r = crud.mark_notification_as_read(notification_id=_nid(999), user_id=1, db=mock_db)
        assert r is None


class TestMarkAllNotificationsAsRead:
    def test_success(self, mock_db):
        import modules.notifications.crud as crud

        result = crud.mark_all_notifications_as_read(user_id=1, db=mock_db)

        assert result is None
        mock_db.execute.assert_called_once()
        mock_db.flush.assert_called_once()


class TestDeleteNotificationsNamingUser:
    @pytest.fixture
    def db(self):
        import modules.notifications.models as m

        session = create_sqlite_session()
        named = {"user_id": 7, "user_name": "Ana", "user_username": "ana"}
        other = {"user_id": 8, "user_name": "Bo", "user_username": "bo"}
        for notification_id, user_id, notification_type, options in [
            (1, 1, 11, named),  # follow request
            (2, 2, 12, named),  # follow accepted
            (3, 3, 41, named),  # admin sign-up approval
            (4, 1, 11, other),
            (5, 1, 1, {"activity_id": "11111111-1111-4111-8111-111111111111"}),
            (6, 2, 21, {}),
            (7, 2, 21, None),
        ]:
            session.add(
                m.Notification(id=_nid(notification_id), user_id=user_id, type=notification_type, options=options)
            )
        session.commit()
        yield session
        session.close()

    def test_deletes_every_owners_notifications_that_name_the_user(self, db):
        import modules.notifications.crud as crud
        import modules.notifications.models as m

        deleted = crud.delete_notifications_naming_user(7, db)
        db.commit()

        assert deleted == 3
        remaining = {n.id for n in db.query(m.Notification).all()}
        assert remaining == {_nid(n) for n in (4, 5, 6, 7)}


class TestDeleteAndMarkSeveral:
    @pytest.fixture
    def db(self):
        import modules.notifications.models as m

        session = create_sqlite_session()
        for notification_id, user_id in [(1, 1), (2, 1), (3, 1), (4, 2)]:
            session.add(
                m.Notification(
                    id=_nid(notification_id),
                    user_id=user_id,
                    type=1,
                    options={"activity_id": "11111111-1111-4111-8111-111111111111"},
                    read=False,
                )
            )
        session.commit()
        yield session
        session.close()

    def test_marking_several_skips_ids_that_are_not_the_users(self, db):
        import modules.notifications.crud as crud
        import modules.notifications.models as m

        crud.mark_notifications_as_read([_nid(1), _nid(4), _nid(99)], user_id=1, db=db)
        db.commit()

        read = {n.id for n in db.query(m.Notification).filter_by(read=True)}
        assert read == {_nid(1)}

    def test_delete_removes_only_the_users_notification(self, db):
        import modules.notifications.crud as crud
        import modules.notifications.models as m

        assert crud.delete_user_notification(_nid(2), user_id=1, db=db) is True
        assert crud.delete_user_notification(_nid(4), user_id=1, db=db) is False
        assert crud.delete_user_notification(_nid(99), user_id=1, db=db) is False
        db.commit()

        assert {n.id for n in db.query(m.Notification)} == {_nid(1), _nid(3), _nid(4)}
