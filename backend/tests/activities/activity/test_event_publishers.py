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


class TestPublishActivityUpdated:
    """An edit must be a fact consumers can subscribe to, not a silent mutation."""

    @patch("modules.activities.activity.event_publishers.platform_publisher")
    def test_delegates_to_facade(self, mock_publisher):
        from modules.activities.activity.event_publishers import publish_activity_updated

        publish_activity_updated(7, 3, ["name"])

        mock_publisher.publish.assert_called_once()
        args, kwargs = mock_publisher.publish.call_args
        assert args[0] == "activity.updated"
        assert args[1] == {"activity_id": 7, "user_id": 3, "changed_fields": ["name"]}
        assert kwargs["source"] == "api:edit_activity"
        assert kwargs["metadata"] == {"activity_id": 7, "user_id": 3}

    @patch("modules.activities.activity.event_publishers.platform_publisher")
    def test_changed_fields_are_sorted(self, mock_publisher):
        """Stable ordering regardless of the producer's iteration order."""
        from modules.activities.activity.event_publishers import publish_activity_updated

        publish_activity_updated(7, 3, {"visibility", "name", "gear_id"})

        assert mock_publisher.publish.call_args.args[1]["changed_fields"] == ["gear_id", "name", "visibility"]

    @patch("modules.activities.activity.event_publishers.platform_publisher")
    def test_commit_path_uses_publish_committing(self, mock_publisher):
        from modules.activities.activity.event_publishers import publish_activity_updated

        db = object()
        commit = MagicMock()
        publish_activity_updated(7, 3, ["name"], db=db, commit=commit)

        mock_publisher.publish_committing.assert_called_once()
        mock_publisher.publish.assert_not_called()
        kwargs = mock_publisher.publish_committing.call_args.kwargs
        assert kwargs["commit"] is commit
        assert kwargs["db"] is db


class TestPublishActivitiesUpdated:
    """A bulk edit emits the same per-row fact as the single edit."""

    @patch("modules.activities.activity.event_publishers.platform_publisher")
    def test_emits_one_event_per_activity_in_one_transaction(self, mock_publisher):
        from modules.activities.activity.event_publishers import publish_activities_updated

        db = object()
        commit = MagicMock()
        publish_activities_updated([4, 5], 2, ["visibility"], db, commit, source="api:bulk_edit_activities")

        mock_publisher.publish_many_committing.assert_called_once()
        args, kwargs = mock_publisher.publish_many_committing.call_args
        assert args[0] == "activity.updated"
        assert args[1] == [
            {"activity_id": 4, "user_id": 2, "changed_fields": ["visibility"]},
            {"activity_id": 5, "user_id": 2, "changed_fields": ["visibility"]},
        ]
        assert kwargs["source"] == "api:bulk_edit_activities"
        assert kwargs["db"] is db
        assert kwargs["commit"] is commit

    @patch("modules.activities.activity.event_publishers.platform_publisher")
    def test_metadata_is_per_activity(self, mock_publisher):
        from modules.activities.activity.event_publishers import publish_activities_updated

        publish_activities_updated([4, 5], 2, ["visibility"], object(), MagicMock(), source="api:bulk")

        metadata_for = mock_publisher.publish_many_committing.call_args.kwargs["metadata_for"]
        assert metadata_for({"activity_id": 4}) == {"activity_id": 4, "user_id": 2}

    @patch("modules.activities.activity.event_publishers.platform_publisher")
    def test_empty_batch_still_commits_once(self, mock_publisher):
        from modules.activities.activity.event_publishers import publish_activities_updated

        commit = MagicMock()
        publish_activities_updated([], 2, ["visibility"], object(), commit, source="api:bulk")

        args, kwargs = mock_publisher.publish_many_committing.call_args
        assert args[1] == []
        assert kwargs["commit"] is commit


class TestPublishActivitiesDeleted:
    """Bulk removals must emit the same fact as the single-activity delete route.

    Without it, unlinking Strava or deleting an account removed the rows silently
    and the thumbnail / source-file cleanup subscribers never ran, orphaning every
    blob those activities owned.
    """

    @patch("modules.activities.activity.event_publishers.platform_publisher")
    def test_emits_one_event_per_activity_in_one_transaction(self, mock_publisher):
        from modules.activities.activity.event_publishers import publish_activities_deleted

        db = object()
        commit = MagicMock()
        publish_activities_deleted([4, 5, 6], 2, db, commit, source="api:delete_user")

        mock_publisher.publish_many_committing.assert_called_once()
        args, kwargs = mock_publisher.publish_many_committing.call_args
        assert args[0] == "activity.deleted"
        assert args[1] == [{"activity_id": 4}, {"activity_id": 5}, {"activity_id": 6}]
        assert kwargs["source"] == "api:delete_user"
        assert kwargs["db"] is db
        assert kwargs["commit"] is commit

    @patch("modules.activities.activity.event_publishers.platform_publisher")
    def test_metadata_is_per_activity(self, mock_publisher):
        from modules.activities.activity.event_publishers import publish_activities_deleted

        publish_activities_deleted([4, 5], 2, object(), MagicMock(), source="api:delete_user")

        metadata_for = mock_publisher.publish_many_committing.call_args.kwargs["metadata_for"]
        assert metadata_for({"activity_id": 4}) == {"activity_id": 4, "user_id": 2}
        assert metadata_for({"activity_id": 5}) == {"activity_id": 5, "user_id": 2}

    @patch("modules.activities.activity.event_publishers.platform_publisher")
    def test_empty_batch_still_commits_once(self, mock_publisher):
        from modules.activities.activity.event_publishers import publish_activities_deleted

        commit = MagicMock()
        publish_activities_deleted([], 2, object(), commit, source="api:delete_user")

        args, kwargs = mock_publisher.publish_many_committing.call_args
        assert args[1] == []
        assert kwargs["commit"] is commit
