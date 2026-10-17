"""Tests for the activities domain event publishers."""

from unittest.mock import MagicMock, patch


class TestPublishActivityCreated:
    @patch("modules.activities.activity.event_publishers.platform_publisher")
    def test_delegates_to_facade(self, mock_publisher):
        from modules.activities.activity.event_publishers import publish_activity_created

        db = object()
        commit = MagicMock()
        publish_activity_created(7, 3, db, commit=commit, source="ingest:upload")

        mock_publisher.publish_committing.assert_called_once()
        args, kwargs = mock_publisher.publish_committing.call_args
        assert args[0] == "activity.created"
        assert args[1] == {"activity_id": 7, "user_id": 3, "duplicate_start_time": False}
        assert kwargs["source"] == "ingest:upload"
        assert kwargs["metadata"] == {"activity_id": 7, "user_id": 3}
        assert kwargs["db"] is db
        assert kwargs["commit"] is commit


class TestPublishActivityDeleted:
    @patch("modules.activities.activity.event_publishers.platform_publisher")
    def test_publishes_atomically_with_the_delete(self, mock_publisher):
        from modules.activities.activity.event_publishers import publish_activity_deleted

        db = object()
        commit = MagicMock()
        publish_activity_deleted(9, 2, db, commit=commit)

        # The atomic path stages + commits the delete and the outbox row together.
        mock_publisher.publish_committing.assert_called_once()
        args, kwargs = mock_publisher.publish_committing.call_args
        assert args[0] == "activity.deleted"
        assert args[1] == {"activity_id": 9}
        assert kwargs["source"] == "api:delete_activity"
        assert kwargs["metadata"] == {"activity_id": 9, "user_id": 2}
        assert kwargs["commit"] is commit
        assert kwargs["db"] is db


class TestPublishActivityUpdated:
    """An edit must be a fact consumers can subscribe to, not a silent mutation."""

    @patch("modules.activities.activity.event_publishers.platform_publisher")
    def test_publishes_atomically_with_the_update(self, mock_publisher):
        from modules.activities.activity.event_publishers import publish_activity_updated

        db = object()
        commit = MagicMock()
        publish_activity_updated(7, 3, db, commit=commit, changed_fields=["name"])

        mock_publisher.publish_committing.assert_called_once()
        args, kwargs = mock_publisher.publish_committing.call_args
        assert args[0] == "activity.updated"
        assert args[1] == {"activity_id": 7, "user_id": 3, "changed_fields": ["name"]}
        assert kwargs["source"] == "api:edit_activity"
        assert kwargs["metadata"] == {"activity_id": 7, "user_id": 3}
        assert kwargs["commit"] is commit
        assert kwargs["db"] is db

    @patch("modules.activities.activity.event_publishers.platform_publisher")
    def test_changed_fields_are_sorted(self, mock_publisher):
        """Stable ordering regardless of the producer's iteration order."""
        from modules.activities.activity.event_publishers import publish_activity_updated

        publish_activity_updated(7, 3, object(), commit=MagicMock(), changed_fields={"visibility", "name", "gear_id"})

        assert mock_publisher.publish_committing.call_args.args[1]["changed_fields"] == [
            "gear_id",
            "name",
            "visibility",
        ]


class TestPublishActivitiesUpdated:
    """A bulk edit emits the same per-row fact as the single edit."""

    @patch("modules.activities.activity.event_publishers.platform_publisher")
    def test_emits_one_event_per_activity_in_one_transaction(self, mock_publisher):
        from modules.activities.activity.event_publishers import publish_activities_updated

        db = object()
        commit = MagicMock()
        publish_activities_updated(
            [4, 5], 2, db, commit=commit, changed_fields=["visibility"], source="api:bulk_edit_activities"
        )

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

        publish_activities_updated(
            [4, 5], 2, object(), commit=MagicMock(), changed_fields=["visibility"], source="api:bulk"
        )

        metadata_for = mock_publisher.publish_many_committing.call_args.kwargs["metadata_for"]
        assert metadata_for({"activity_id": 4}) == {"activity_id": 4, "user_id": 2}

    @patch("modules.activities.activity.event_publishers.platform_publisher")
    def test_declares_the_payload_version_it_writes(self, mock_publisher):
        from modules.activities.activity.event_publishers import publish_activities_updated
        from modules.activities.activity.events import ActivityUpdatedPayload

        publish_activities_updated([4], 2, object(), commit=MagicMock(), changed_fields=["name"], source="api:bulk")

        kwargs = mock_publisher.publish_many_committing.call_args.kwargs
        assert kwargs["schema_version"] == ActivityUpdatedPayload.SCHEMA_VERSION

    @patch("modules.activities.activity.event_publishers.platform_publisher")
    def test_a_bulk_delete_declares_the_payload_version_it_writes(self, mock_publisher):
        from modules.activities.activity.event_publishers import publish_activities_deleted
        from modules.activities.activity.events import ActivityDeletedPayload

        publish_activities_deleted([4], 2, object(), commit=MagicMock(), source="api:bulk")

        kwargs = mock_publisher.publish_many_committing.call_args.kwargs
        assert kwargs["schema_version"] == ActivityDeletedPayload.SCHEMA_VERSION

    @patch("modules.activities.activity.event_publishers.platform_publisher")
    def test_empty_batch_still_commits_once(self, mock_publisher):
        from modules.activities.activity.event_publishers import publish_activities_updated

        commit = MagicMock()
        publish_activities_updated([], 2, object(), commit=commit, changed_fields=["visibility"], source="api:bulk")

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
        publish_activities_deleted([4, 5, 6], 2, db, commit=commit, source="api:delete_user")

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

        publish_activities_deleted([4, 5], 2, object(), commit=MagicMock(), source="api:delete_user")

        metadata_for = mock_publisher.publish_many_committing.call_args.kwargs["metadata_for"]
        assert metadata_for({"activity_id": 4}) == {"activity_id": 4, "user_id": 2}
        assert metadata_for({"activity_id": 5}) == {"activity_id": 5, "user_id": 2}

    @patch("modules.activities.activity.event_publishers.platform_publisher")
    def test_empty_batch_still_commits_once(self, mock_publisher):
        from modules.activities.activity.event_publishers import publish_activities_deleted

        commit = MagicMock()
        publish_activities_deleted([], 2, object(), commit=commit, source="api:delete_user")

        args, kwargs = mock_publisher.publish_many_committing.call_args
        assert args[1] == []
        assert kwargs["commit"] is commit
