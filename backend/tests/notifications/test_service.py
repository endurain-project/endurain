"""Tests for the notifications application layer."""

from unittest.mock import MagicMock, patch

import pytest

import core.exceptions as core_exceptions
import modules.notifications.constants as notifications_constants
import modules.notifications.service as notifications_service


class TestReadsAndMarks:
    def test_count_delegates_to_crud(self, mock_db):
        with patch("modules.notifications.service.notifications_crud.get_user_notifications_count", return_value=3):
            assert notifications_service.count_notifications(1, mock_db) == 3

    def test_list_passes_the_window(self, mock_db):
        with patch(
            "modules.notifications.service.notifications_crud.get_user_notifications_with_pagination", return_value=[]
        ) as crud_list:
            notifications_service.list_notifications(1, mock_db, page_number=2, num_records=5)
        crud_list.assert_called_once_with(1, mock_db, 2, 5)

    def test_mark_read_commits(self, mock_db):
        with patch("modules.notifications.service.notifications_crud.mark_notification_as_read") as mark:
            notifications_service.mark_notification_as_read(4, 1, mock_db)
        mark.assert_called_once_with(4, 1, mock_db)
        mock_db.commit.assert_called_once()

    def test_mark_all_read_commits(self, mock_db):
        with patch("modules.notifications.service.notifications_crud.mark_all_notifications_as_read") as mark:
            notifications_service.mark_all_notifications_as_read(1, mock_db)
        mark.assert_called_once_with(1, mock_db)
        mock_db.commit.assert_called_once()


class TestCreateActivityCreatedNotification:
    def test_new_activity_variant(self, mock_db):
        stored = MagicMock(id=9)
        with patch(
            "modules.notifications.service.notifications_crud.create_notification_once", return_value=(stored, True)
        ) as create_once:
            notification, ws_message, created = notifications_service.create_activity_created_notification(
                1, 5, False, "event-1", mock_db
            )

        data = create_once.call_args.args[0]
        assert data.type == notifications_constants.NotificationType.NEW_ACTIVITY
        assert data.source_event_id == "event-1"
        assert data.options == {"activity_id": 5}
        assert (notification, ws_message, created) == (stored, notifications_constants.NEW_ACTIVITY_WS_MESSAGE, True)
        mock_db.commit.assert_called_once()

    def test_duplicate_variant(self, mock_db):
        with patch(
            "modules.notifications.service.notifications_crud.create_notification_once",
            return_value=(MagicMock(id=9), True),
        ) as create_once:
            _, ws_message, _ = notifications_service.create_activity_created_notification(
                1, 5, True, "event-1", mock_db
            )

        assert create_once.call_args.args[0].type == notifications_constants.NotificationType.DUPLICATE_ACTIVITY
        assert ws_message == notifications_constants.DUPLICATE_ACTIVITY_WS_MESSAGE

    def test_replayed_event_reports_not_created(self, mock_db):
        with patch(
            "modules.notifications.service.notifications_crud.create_notification_once",
            return_value=(MagicMock(id=9), False),
        ):
            _, _, created = notifications_service.create_activity_created_notification(1, 5, False, "event-1", mock_db)
        assert created is False


class TestCreateFollowNotifications:
    def test_follow_request_names_the_requester(self, mock_db):
        requester = MagicMock()
        requester.name = "Ann"
        requester.username = "ann"
        with (
            patch("modules.notifications.service.users_integration.get_user", return_value=requester),
            patch(
                "modules.notifications.service.notifications_crud.create_notification_once",
                return_value=(MagicMock(id=3), True),
            ) as create_once,
        ):
            _, ws_message, created = notifications_service.create_follow_request_notification(1, 2, "event-1", mock_db)

        data = create_once.call_args.args[0]
        assert data.user_id == 2
        assert data.type == notifications_constants.NotificationType.NEW_FOLLOWER_REQUEST
        assert data.options == {"user_id": 1, "user_name": "Ann", "user_username": "ann"}
        assert ws_message == notifications_constants.NEW_FOLLOWER_REQUEST_WS_MESSAGE
        assert created is True
        mock_db.commit.assert_called_once()

    def test_follow_request_requires_the_requester(self, mock_db):
        with (
            patch("modules.notifications.service.users_integration.get_user", return_value=None),
            pytest.raises(core_exceptions.NotFoundError),
        ):
            notifications_service.create_follow_request_notification(1, 2, "event-1", mock_db)
        mock_db.commit.assert_not_called()

    def test_follow_accepted_notifies_the_requester(self, mock_db):
        accepter = MagicMock()
        accepter.name = "Bob"
        accepter.username = "bob"
        with (
            patch("modules.notifications.service.users_integration.get_user", return_value=accepter),
            patch(
                "modules.notifications.service.notifications_crud.create_notification_once",
                return_value=(MagicMock(id=3), True),
            ) as create_once,
        ):
            _, ws_message, _ = notifications_service.create_follow_accepted_notification(2, 1, "event-1", mock_db)

        data = create_once.call_args.args[0]
        assert data.user_id == 1
        assert data.type == notifications_constants.NotificationType.NEW_FOLLOWER_REQUEST_ACCEPTED
        assert data.options == {"user_id": 2, "user_name": "Bob", "user_username": "bob"}
        assert ws_message == notifications_constants.NEW_FOLLOWER_REQUEST_ACCEPTED_WS_MESSAGE

    def test_follow_accepted_requires_the_accepter(self, mock_db):
        with (
            patch("modules.notifications.service.users_integration.get_user", return_value=None),
            pytest.raises(core_exceptions.NotFoundError),
        ):
            notifications_service.create_follow_accepted_notification(2, 1, "event-1", mock_db)
