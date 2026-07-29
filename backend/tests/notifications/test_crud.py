from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy.exc import SQLAlchemyError

import core.exceptions as core_exceptions


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

    def test_db_error(self, mock_db):
        import modules.notifications.crud as crud

        mock_db.execute.side_effect = SQLAlchemyError("err")
        with pytest.raises(core_exceptions.ProcessingError) as e:
            crud.get_user_notification_by_id(notification_id=1, user_id=1, db=mock_db)
        assert e.value.status_code == 500


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

    def test_db_error(self, mock_db):
        import modules.notifications.crud as crud

        mock_db.execute.side_effect = SQLAlchemyError("err")
        with pytest.raises(core_exceptions.ProcessingError) as e:
            crud.get_user_notifications_count(user_id=1, db=mock_db)
        assert e.value.status_code == 500


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

    def test_db_error(self, mock_db):
        import modules.notifications.crud as crud

        mock_db.execute.side_effect = SQLAlchemyError("err")
        with pytest.raises(core_exceptions.ProcessingError) as e:
            crud.get_user_notifications_with_pagination(user_id=1, db=mock_db)
        assert e.value.status_code == 500


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
        mock_db.commit.assert_called_once()
        mock_db.refresh.assert_called_once()

    def test_db_error(self, mock_db):
        from pydantic import BaseModel

        import modules.notifications.crud as crud

        mock_db.add.side_effect = SQLAlchemyError("err")

        class NC(BaseModel):
            user_id: int = 1
            type: str = "follow_request"
            options: dict = {}

        with pytest.raises(core_exceptions.ProcessingError) as e:
            crud.create_notification(notification=NC(), db=mock_db)
        assert e.value.status_code == 500


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
        mock_db.commit.assert_called_once()
        mock_db.refresh.assert_called_once_with(n)

    def test_not_found(self, mock_db):
        import modules.notifications.crud as crud

        mock_db.execute.return_value.scalars.return_value.first.return_value = None
        r = crud.mark_notification_as_read(notification_id=999, user_id=1, db=mock_db)
        assert r is None

    def test_db_error(self, mock_db):
        import modules.notifications.crud as crud
        import modules.notifications.models as m

        n = MagicMock(spec=m.Notification, id=1, user_id=1, read=False)
        mock_db.execute.return_value.scalars.return_value.first.return_value = n
        mock_db.commit.side_effect = SQLAlchemyError("err")

        with pytest.raises(core_exceptions.ProcessingError) as e:
            crud.mark_notification_as_read(notification_id=1, user_id=1, db=mock_db)
        assert e.value.status_code == 500


class TestMarkAllNotificationsAsRead:
    def test_success(self, mock_db):
        import modules.notifications.crud as crud

        result = crud.mark_all_notifications_as_read(user_id=1, db=mock_db)

        assert result is None
        mock_db.execute.assert_called_once()
        mock_db.commit.assert_called_once()

    def test_db_error(self, mock_db):
        import modules.notifications.crud as crud

        mock_db.execute.side_effect = SQLAlchemyError("err")

        with pytest.raises(core_exceptions.ProcessingError) as e:
            crud.mark_all_notifications_as_read(user_id=1, db=mock_db)
        assert e.value.status_code == 500
