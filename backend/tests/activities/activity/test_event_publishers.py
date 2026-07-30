"""Tests for the activities domain event publishers."""

from unittest.mock import patch


class TestPublishActivityCreated:
    @patch("modules.activities.activity.event_publishers.platform_publisher")
    def test_delegates_to_facade(self, mock_publisher):
        from modules.activities.activity.event_publishers import publish_activity_created

        publish_activity_created(7, 3)

        mock_publisher.publish.assert_called_once()
        args, kwargs = mock_publisher.publish.call_args
        assert args[0] == "activity.created"
        assert args[1] == {"activity_id": 7, "user_id": 3}
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
