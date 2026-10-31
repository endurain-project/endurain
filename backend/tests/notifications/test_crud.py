from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy.exc import IntegrityError

import core.exceptions as core_exceptions
from tests._helpers.db import create_sqlite_session


class TestGetUserNotificationById:
    def test_success(self, mock_db):
        import modules.notifications.crud as crud
        import modules.notifications.models as m

        n = MagicMock(
            spec=m.Notification, id=1, user_id=1, type=1, read=False, options=None, created_at=datetime(2024, 1, 1)
        )
        mock_db.execute.return_value.scalars.return_value.first.return_value = n
        r = crud.get_user_notification_by_id(notification_id=1, user_id=1, db=mock_db)
        assert r is not None
        assert r.id == 1
        assert r.user_id == 1

    def test_not_found(self, mock_db):
        import modules.notifications.crud as crud

        mock_db.execute.return_value.scalars.return_value.first.return_value = None
        r = crud.get_user_notification_by_id(notification_id=999, user_id=1, db=mock_db)
        assert r is None


class TestGetUserNotificationsCount:
    def test_success(self, mock_db):
        import modules.notifications.crud as crud

        mock_db.execute.return_value.scalar_one.return_value = 7
        r = crud.get_user_notifications_count(user_id=1, db=mock_db)
        assert r == 7

    def test_zero(self, mock_db):
        import modules.notifications.crud as crud

        mock_db.execute.return_value.scalar_one.return_value = 0
        r = crud.get_user_notifications_count(user_id=1, db=mock_db)
        assert r == 0


class TestGetUserNotificationsWithPagination:
    def test_success(self, mock_db):
        import modules.notifications.crud as crud
        import modules.notifications.models as m

        n = MagicMock(
            spec=m.Notification, id=1, user_id=1, type=1, read=False, options=None, created_at=datetime(2024, 1, 1)
        )
        mock_db.execute.return_value.scalars.return_value.all.return_value = [n]
        r = crud.get_user_notifications_with_pagination(user_id=1, db=mock_db, page_number=1, num_records=5)
        assert len(r) == 1
        assert r[0].id == 1
        assert r[0].user_id == 1

    def test_page_two(self, mock_db):
        import modules.notifications.crud as crud

        mock_db.execute.return_value.scalars.return_value.all.return_value = []
        r = crud.get_user_notifications_with_pagination(user_id=1, db=mock_db, page_number=2, num_records=5)
        assert r == []

    def test_empty(self, mock_db):
        import modules.notifications.crud as crud

        mock_db.execute.return_value.scalars.return_value.all.return_value = []
        r = crud.get_user_notifications_with_pagination(user_id=1, db=mock_db)
        assert r == []


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
                    id=notification_id,
                    user_id=user_id,
                    type=1,
                    read=read,
                    created_at=datetime(2024, 1, notification_id),
                )
            )
        session.commit()
        yield session
        session.close()

    def test_count_includes_read_notifications_by_default(self, db):
        import modules.notifications.crud as crud

        assert crud.get_user_notifications_count(user_id=1, db=db) == 5

    def test_count_unread_only_skips_read_and_other_users_notifications(self, db):
        import modules.notifications.crud as crud

        assert crud.get_user_notifications_count(user_id=1, db=db, unread_only=True) == 3

    def test_count_unread_only_is_zero_once_everything_is_read(self, db):
        import modules.notifications.crud as crud

        crud.mark_all_notifications_as_read(1, db)

        assert crud.get_user_notifications_count(user_id=1, db=db, unread_only=True) == 0

    def test_page_unread_only_returns_the_unread_ones_newest_first(self, db):
        import modules.notifications.crud as crud

        page = crud.get_user_notifications_with_pagination(user_id=1, db=db, num_records=10, unread_only=True)

        assert [n.id for n in page] == [5, 4, 2]
        assert all(not n.read for n in page)

    def test_page_unread_only_pages_over_the_filtered_rows(self, db):
        import modules.notifications.crud as crud

        second = crud.get_user_notifications_with_pagination(
            user_id=1, db=db, page_number=2, num_records=2, unread_only=True
        )

        assert [n.id for n in second] == [2]

    def test_page_includes_read_notifications_by_default(self, db):
        import modules.notifications.crud as crud

        page = crud.get_user_notifications_with_pagination(user_id=1, db=db, num_records=10)

        assert [n.id for n in page] == [5, 4, 3, 2, 1]


class TestCreateNotification:
    def test_success(self, mock_db):
        import modules.notifications.crud as crud
        import modules.notifications.schema as schema

        notification_data = schema.NotificationCreate(user_id=1, type=1, options={})

        mock_notification = MagicMock()
        mock_notification.id = 1
        mock_notification.user_id = 1
        mock_notification.type = 1
        mock_notification.read = False
        mock_notification.options = None
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
            type=11,
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
            type=11,
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
            type=11,
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
            spec=m.Notification, id=1, user_id=1, type=1, read=False, options=None, created_at=datetime(2024, 1, 1)
        )
        mock_db.execute.return_value.scalars.return_value.first.return_value = n

        r = crud.mark_notification_as_read(notification_id=1, user_id=1, db=mock_db)
        assert n.read is True
        assert r is not None
        assert r.id == 1
        assert r.user_id == 1
        mock_db.flush.assert_called_once()
        mock_db.refresh.assert_called_once_with(n)

    def test_not_found(self, mock_db):
        import modules.notifications.crud as crud

        mock_db.execute.return_value.scalars.return_value.first.return_value = None
        r = crud.mark_notification_as_read(notification_id=999, user_id=1, db=mock_db)
        assert r is None


class TestMarkAllNotificationsAsRead:
    def test_success(self, mock_db):
        import modules.notifications.crud as crud

        result = crud.mark_all_notifications_as_read(user_id=1, db=mock_db)

        assert result is None
        mock_db.execute.assert_called_once()
        mock_db.flush.assert_called_once()
