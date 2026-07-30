"""Tests for the activities domain event publishers."""

from unittest.mock import MagicMock, patch


class TestPublishActivityCreated:
    @patch("modules.activities.activity.event_publishers.platform_publisher")
    def test_delegates_to_facade(self, mock_publisher):
        from modules.activities.activity.event_publishers import publish_activity_created

        publish_activity_created(7, 3)

        mock_publisher.publish.assert_called_once()
        args, kwargs = mock_publisher.publish.call_args
        assert args[0] == "activity.created"
        assert args[1] == {"activity_id": 7, "user_id": 3, "duplicate_start_time": False}
        assert kwargs["source"] == "api:store_activity"
        assert kwargs["metadata"] == {"activity_id": 7, "user_id": 3}


class TestPublishActivityDeleted:
    @patch("modules.activities.activity.event_publishers.platform_publisher")
    def test_delegates_to_facade(self, mock_publisher):
        from modules.activities.activity.event_publishers import publish_activity_deleted

        publish_activity_deleted(9, 2)

        mock_publisher.publish.assert_called_once()
        args, kwargs = mock_publisher.publish.call_args
        assert args[0] == "activity.deleted"
        assert args[1] == {"activity_id": 9}
        assert kwargs["source"] == "api:delete_activity"
        assert kwargs["metadata"] == {"activity_id": 9, "user_id": 2}

    @patch("modules.activities.activity.event_publishers.platform_publisher")
    def test_commit_path_uses_publish_committing(self, mock_publisher):
        from modules.activities.activity.event_publishers import publish_activity_deleted

        db = object()
        commit = MagicMock()
        publish_activity_deleted(9, 2, db=db, commit=commit)

        # The atomic path stages + commits the delete and the outbox row together.
        mock_publisher.publish_committing.assert_called_once()
        mock_publisher.publish.assert_not_called()
        args, kwargs = mock_publisher.publish_committing.call_args
        assert args[0] == "activity.deleted"
        assert args[1] == {"activity_id": 9}
        assert kwargs["commit"] is commit
        assert kwargs["db"] is db
