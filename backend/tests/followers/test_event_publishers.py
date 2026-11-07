"""Tests for the followers event publishers."""

from unittest.mock import MagicMock, patch

import core.event_metadata as core_event_metadata


class TestPublishFollowerRequested:
    @patch("modules.followers.event_publishers.platform_publisher")
    def test_publishes_with_payload_and_metadata(self, mock_publisher):

        import modules.followers.events as followers_events
        from modules.followers.event_publishers import publish_follower_requested

        db = object()
        commit = MagicMock()
        publish_follower_requested(1, 2, db, commit=commit)

        mock_publisher.publish_committing.assert_called_once()
        args, kwargs = mock_publisher.publish_committing.call_args
        assert args[0] == followers_events.FOLLOWER_REQUESTED
        assert args[1] == {"requester_user_id": 1, "target_user_id": 2}
        assert kwargs["schema_version"] == followers_events.FollowerRequestedPayload.SCHEMA_VERSION
        assert kwargs["metadata"] == {core_event_metadata.META_USER_ID: 2}
        assert kwargs["db"] is db
        assert kwargs["commit"] is commit


class TestPublishFollowerAccepted:
    @patch("modules.followers.event_publishers.platform_publisher")
    def test_publishes_with_payload_and_metadata(self, mock_publisher):

        import modules.followers.events as followers_events
        from modules.followers.event_publishers import publish_follower_accepted

        db = object()
        commit = MagicMock()
        publish_follower_accepted(1, 2, db, commit=commit)

        mock_publisher.publish_committing.assert_called_once()
        args, kwargs = mock_publisher.publish_committing.call_args
        assert args[0] == followers_events.FOLLOWER_ACCEPTED
        assert args[1] == {"accepter_user_id": 1, "requester_user_id": 2}
        assert kwargs["schema_version"] == followers_events.FollowerAcceptedPayload.SCHEMA_VERSION
        assert kwargs["metadata"] == {core_event_metadata.META_USER_ID: 2}
        assert kwargs["db"] is db
        assert kwargs["commit"] is commit


class TestPublishFollowerRequestRemoved:
    @patch("modules.followers.event_publishers.platform_publisher")
    def test_publishes_with_payload_and_metadata(self, mock_publisher):
        import modules.followers.events as followers_events
        from modules.followers.event_publishers import publish_follower_request_removed

        db = object()
        commit = MagicMock()
        publish_follower_request_removed(1, 2, db, commit=commit, source="api:test")

        args, kwargs = mock_publisher.publish_committing.call_args
        assert args[0] == followers_events.FOLLOWER_REQUEST_REMOVED
        assert args[1] == {"requester_user_id": 1, "target_user_id": 2}
        assert kwargs["source"] == "api:test"
        assert kwargs["schema_version"] == followers_events.FollowerRequestRemovedPayload.SCHEMA_VERSION
        assert kwargs["metadata"] == {core_event_metadata.META_USER_ID: 2}
        assert kwargs["db"] is db
        assert kwargs["commit"] is commit
