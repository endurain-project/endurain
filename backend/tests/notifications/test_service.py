"""Tests for the notifications application layer."""

from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock, patch

import pytest

import core.database as core_database
import core.exceptions as core_exceptions
import core.pagination as core_pagination
import modules.notifications.constants as notifications_constants
import modules.notifications.service as notifications_service


def _read(notification_id: int):
    import modules.notifications.schema as notifications_schema

    return notifications_schema.NOTIFICATION_READ_ADAPTER.validate_python(
        {
            "id": notification_id,
            "user_id": 1,
            "type": "new_activity",
            "options": {"activity_id": notification_id},
            "created_at": datetime(2024, 1, notification_id, tzinfo=UTC),
        }
    )


class TestReadsAndMarks:
    def test_unread_count_counts_only_unread(self, mock_db):
        with patch(
            "modules.notifications.service.notifications_crud.count_user_unread_notifications", return_value=3
        ) as crud_count:
            assert notifications_service.count_unread_notifications(1, mock_db) == 3
        crud_count.assert_called_once_with(1, mock_db)

    def test_list_returns_a_slice_without_a_cursor_when_nothing_follows(self, mock_db):
        rows = [_read(1), _read(2)]
        with patch(
            "modules.notifications.service.notifications_crud.get_user_notifications_after", return_value=rows
        ) as crud_list:
            page = notifications_service.list_notifications(1, mock_db, cursor=None, num_records=5)
        crud_list.assert_called_once_with(1, None, 6, mock_db, unread_only=False)
        assert [n.id for n in page.items] == [1, 2]
        assert page.num_records == 5
        assert page.next_cursor is None

    def test_list_over_fetches_one_row_and_cursors_on_the_last_kept_row(self, mock_db):
        rows = [_read(3), _read(2), _read(1)]
        with patch(
            "modules.notifications.service.notifications_crud.get_user_notifications_after", return_value=rows
        ) as crud_list:
            page = notifications_service.list_notifications(1, mock_db, cursor=None, num_records=2, unread_only=True)
        crud_list.assert_called_once_with(1, None, 3, mock_db, unread_only=True)
        assert [n.id for n in page.items] == [3, 2]
        assert page.next_cursor is not None
        assert core_pagination.decode_cursor(page.next_cursor) == (rows[1].created_at, 2)

    def test_list_resumes_after_the_decoded_cursor(self, mock_db):
        position = (datetime(2024, 1, 2, tzinfo=UTC), 2)
        cursor = core_pagination.encode_cursor(*position)
        with patch(
            "modules.notifications.service.notifications_crud.get_user_notifications_after", return_value=[]
        ) as crud_list:
            notifications_service.list_notifications(1, mock_db, cursor=cursor, num_records=2)
        crud_list.assert_called_once_with(1, position, 3, mock_db, unread_only=False)

    def test_list_rejects_a_cursor_the_server_did_not_issue(self, mock_db):
        with pytest.raises(core_exceptions.InvalidInputError):
            notifications_service.list_notifications(1, mock_db, cursor="garbage", num_records=2)

    def test_get_missing_notification_raises(self, mock_db):
        with (
            patch("modules.notifications.service.notifications_crud.get_user_notification_by_id", return_value=None),
            pytest.raises(core_exceptions.NotFoundError),
        ):
            notifications_service.get_notification(4, 1, mock_db)

    def test_mark_read_commits(self, mock_db):
        with patch("modules.notifications.service.notifications_crud.mark_notification_as_read") as mark:
            notifications_service.mark_notification_as_read(4, 1, mock_db)
        mark.assert_called_once_with(4, 1, mock_db)
        mock_db.commit.assert_called_once()

    def test_mark_read_missing_raises_without_commit(self, mock_db):
        with (
            patch("modules.notifications.service.notifications_crud.mark_notification_as_read", return_value=None),
            pytest.raises(core_exceptions.NotFoundError),
        ):
            notifications_service.mark_notification_as_read(4, 1, mock_db)
        mock_db.commit.assert_not_called()

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
        requester = MagicMock(id=1)
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
        accepter = MagicMock(id=2)
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


class TestPurgeReadNotifications:
    @staticmethod
    def _retention(days):
        return patch(
            "modules.notifications.service.server_settings_integration.get_read_notification_retention_days",
            return_value=days,
        )

    def test_deletes_read_notifications_older_than_the_stored_days(self, mock_db):
        batch = core_database.PURGE_BATCH_SIZE
        with (
            self._retention(30) as retention,
            patch(
                "modules.notifications.service.notifications_crud.delete_read_notifications_before",
                side_effect=[batch, 4],
            ) as delete,
        ):
            before = datetime.now(UTC)
            removed = notifications_service.delete_read_notifications(mock_db)
        retention.assert_called_once_with(mock_db)
        assert removed == batch + 4
        assert delete.call_count == 2
        cutoff = delete.call_args.args[0]
        assert before - timedelta(days=30, seconds=5) < cutoff < before - timedelta(days=30) + timedelta(seconds=5)
        assert mock_db.commit.call_count == 2

    def test_zero_disables_pruning(self, mock_db):
        with (
            self._retention(0),
            patch("modules.notifications.service.notifications_crud.delete_read_notifications_before") as delete,
        ):
            assert notifications_service.delete_read_notifications(mock_db) == 0
        delete.assert_not_called()
        mock_db.commit.assert_not_called()


class TestDeleteAndMarkSeveral:
    def test_delete_commits_when_the_notification_was_deleted(self, mock_db):
        with patch("modules.notifications.service.notifications_crud.delete_user_notification", return_value=True):
            notifications_service.delete_notification(3, 1, mock_db)

        mock_db.commit.assert_called_once()

    def test_delete_of_someone_elses_notification_is_not_found(self, mock_db):
        with (
            patch("modules.notifications.service.notifications_crud.delete_user_notification", return_value=False),
            pytest.raises(core_exceptions.NotFoundError),
        ):
            notifications_service.delete_notification(3, 1, mock_db)

        mock_db.commit.assert_not_called()

    def test_marking_several_commits_once(self, mock_db):
        with patch("modules.notifications.service.notifications_crud.mark_notifications_as_read") as crud_mark:
            notifications_service.mark_notifications_as_read([1, 2], 1, mock_db)

        crud_mark.assert_called_once_with([1, 2], 1, mock_db)
        mock_db.commit.assert_called_once()
