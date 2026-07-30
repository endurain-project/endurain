"""Tests for the activity lifecycle thumbnail subscribers."""

from unittest.mock import MagicMock, patch

import pytest

from core.platform.events import new_event


class TestOnActivityCreatedGenerateThumbnail:
    @staticmethod
    def _event(payload):
        return new_event("activity.created", payload, source="test")

    @patch("activities.activity_thumbnail.subscribers.platform_runtime")
    def test_noop_for_non_int_activity_id(self, mock_runtime):
        from activities.activity_thumbnail.subscribers import on_activity_created_generate_thumbnail

        on_activity_created_generate_thumbnail(self._event({"activity_id": "x", "user_id": 2}))

        mock_runtime.get_active_platform.assert_not_called()

    @patch("activities.activity_thumbnail.subscribers.platform_runtime")
    def test_noop_when_user_id_missing(self, mock_runtime):
        from activities.activity_thumbnail.subscribers import on_activity_created_generate_thumbnail

        # The owner id is required to load the activity's stream; without it, skip.
        on_activity_created_generate_thumbnail(self._event({"activity_id": 1}))

        mock_runtime.get_active_platform.assert_not_called()

    @patch("activities.activity_thumbnail.service.generate_and_store_thumbnail")
    @patch("activities.activity_thumbnail.service.resolve_tile_settings")
    @patch("activities.activity_thumbnail.subscribers.activity_streams_crud")
    @patch("activities.activity_thumbnail.subscribers.core_database.SessionLocal")
    @patch("activities.activity_thumbnail.subscribers.platform_runtime")
    def test_noop_when_stream_missing(self, mock_runtime, mock_session, mock_streams, mock_resolve, mock_generate):
        from activities.activity_thumbnail.subscribers import on_activity_created_generate_thumbnail

        mock_session.return_value.__enter__.return_value = MagicMock()
        mock_streams.get_activity_stream_by_type.return_value = None

        on_activity_created_generate_thumbnail(self._event({"activity_id": 1, "user_id": 2}))

        mock_resolve.assert_not_called()
        mock_generate.assert_not_called()

    @patch("activities.activity_thumbnail.service.generate_and_store_thumbnail")
    @patch("activities.activity_thumbnail.service.resolve_tile_settings")
    @patch("activities.activity_thumbnail.subscribers.activity_streams_crud")
    @patch("activities.activity_thumbnail.subscribers.core_database.SessionLocal")
    @patch("activities.activity_thumbnail.subscribers.platform_runtime")
    def test_noop_when_too_few_waypoints(self, mock_runtime, mock_session, mock_streams, mock_resolve, mock_generate):
        from activities.activity_thumbnail.subscribers import on_activity_created_generate_thumbnail

        mock_session.return_value.__enter__.return_value = MagicMock()
        mock_streams.get_activity_stream_by_type.return_value = MagicMock(stream_waypoints=[{"lat": 1.0, "lon": 2.0}])

        on_activity_created_generate_thumbnail(self._event({"activity_id": 1, "user_id": 2}))

        mock_resolve.assert_not_called()
        mock_generate.assert_not_called()

    @patch("activities.activity_thumbnail.service.generate_and_store_thumbnail")
    @patch("activities.activity_thumbnail.service.resolve_tile_settings")
    @patch("activities.activity_thumbnail.subscribers.activity_streams_crud")
    @patch("activities.activity_thumbnail.subscribers.core_database.SessionLocal")
    @patch("activities.activity_thumbnail.subscribers.platform_runtime")
    def test_generates_for_gps_activity(self, mock_runtime, mock_session, mock_streams, mock_resolve, mock_generate):
        from activities.activity_thumbnail.subscribers import on_activity_created_generate_thumbnail

        db = MagicMock()
        mock_session.return_value.__enter__.return_value = db
        storage = MagicMock()
        mock_runtime.get_active_platform.return_value.storage = storage
        waypoints = [{"lat": 1.0, "lon": 2.0}, {"lat": 1.1, "lon": 2.1}]
        mock_streams.get_activity_stream_by_type.return_value = MagicMock(stream_waypoints=waypoints)
        mock_resolve.return_value = ("u", "#fff", None)

        on_activity_created_generate_thumbnail(self._event({"activity_id": 5, "user_id": 9}))

        # The owner (user_id) from the payload is threaded into the ownership-checked query.
        stream_args = mock_streams.get_activity_stream_by_type.call_args.args
        assert stream_args[0] == 5
        assert stream_args[2] == 9
        assert stream_args[3] is db
        mock_generate.assert_called_once()
        gen_args = mock_generate.call_args.args
        assert gen_args[0] == 5
        assert gen_args[1] == waypoints
        assert gen_args[2] is storage

    @patch("activities.activity_thumbnail.subscribers.core_logger")
    @patch("activities.activity_thumbnail.subscribers.platform_runtime")
    def test_swallows_errors(self, mock_runtime, mock_logger):
        from activities.activity_thumbnail.subscribers import on_activity_created_generate_thumbnail

        mock_runtime.get_active_platform.side_effect = RuntimeError("boom")

        # Must not raise — a thumbnail failure never breaks activity import.
        on_activity_created_generate_thumbnail(self._event({"activity_id": 1, "user_id": 2}))

        mock_logger.print_to_log.assert_called()


class TestOnActivityDeletedCleanupThumbnail:
    @staticmethod
    def _event(payload):
        return new_event("activity.deleted", payload, source="test")

    @patch("activities.activity_thumbnail.subscribers.platform_runtime")
    def test_noop_for_non_int_payload(self, mock_runtime):
        from activities.activity_thumbnail.subscribers import on_activity_deleted_cleanup_thumbnail

        on_activity_deleted_cleanup_thumbnail(self._event({"activity_id": None}))

        mock_runtime.get_active_platform.assert_not_called()

    @patch("activities.activity_thumbnail.service.delete_activity_thumbnail")
    @patch("activities.activity_thumbnail.subscribers.platform_runtime")
    def test_deletes_thumbnail(self, mock_runtime, mock_delete):
        from activities.activity_thumbnail.subscribers import on_activity_deleted_cleanup_thumbnail

        storage = MagicMock()
        mock_runtime.get_active_platform.return_value.storage = storage

        on_activity_deleted_cleanup_thumbnail(self._event({"activity_id": 9}))

        mock_delete.assert_called_once_with(9, storage)

    @patch("activities.activity_thumbnail.service.delete_activity_thumbnail")
    @patch("activities.activity_thumbnail.subscribers.core_logger")
    @patch("activities.activity_thumbnail.subscribers.platform_runtime")
    def test_swallows_errors(self, mock_runtime, mock_logger, mock_delete):
        from activities.activity_thumbnail.subscribers import on_activity_deleted_cleanup_thumbnail

        mock_delete.side_effect = OSError("boom")
        mock_runtime.get_active_platform.return_value.storage = MagicMock()

        # Must not raise — a cleanup failure never breaks activity deletion.
        on_activity_deleted_cleanup_thumbnail(self._event({"activity_id": 1}))

        mock_logger.print_to_log.assert_called()


class TestRegisterThumbnailSubscribers:
    def test_subscribes_to_created_and_deleted(self):
        from activities.activity_thumbnail.subscribers import (
            on_activity_created_generate_thumbnail,
            on_activity_deleted_cleanup_thumbnail,
            register_thumbnail_subscribers,
        )

        events = MagicMock()
        register_thumbnail_subscribers(events)

        assert events.subscribe.call_count == 2
        events.subscribe.assert_any_call("activity.created", on_activity_created_generate_thumbnail)
        events.subscribe.assert_any_call("activity.deleted", on_activity_deleted_cleanup_thumbnail)


class TestDurableThumbnailHandlers:
    @patch("activities.activity_thumbnail.subscribers.platform_runtime")
    def test_generate_core_noops_without_owner(self, mock_runtime):
        from activities.activity_thumbnail.subscribers import generate_activity_thumbnail_for_event

        # No user_id -> nothing to do; the core returns (job completes, not fails).
        generate_activity_thumbnail_for_event(new_event("activity.created", {"activity_id": 1}, source="test"))

        mock_runtime.get_active_platform.assert_not_called()

    @patch("activities.activity_thumbnail.subscribers.platform_runtime")
    def test_generate_core_raises_on_error(self, mock_runtime):
        from activities.activity_thumbnail.subscribers import generate_activity_thumbnail_for_event

        mock_runtime.get_active_platform.side_effect = RuntimeError("boom")

        # The durable core propagates so the runner can retry/dead-letter.
        with pytest.raises(RuntimeError):
            generate_activity_thumbnail_for_event(
                new_event("activity.created", {"activity_id": 1, "user_id": 2}, source="test")
            )

    @patch("activities.activity_thumbnail.service.delete_activity_thumbnail")
    @patch("activities.activity_thumbnail.subscribers.platform_runtime")
    def test_cleanup_core_raises_on_error(self, mock_runtime, mock_delete):
        from activities.activity_thumbnail.subscribers import cleanup_activity_thumbnail_for_event

        mock_delete.side_effect = OSError("boom")
        mock_runtime.get_active_platform.return_value.storage = MagicMock()

        with pytest.raises(OSError):
            cleanup_activity_thumbnail_for_event(new_event("activity.deleted", {"activity_id": 1}, source="test"))

    def test_register_durable_handlers(self):
        from activities.activity_thumbnail.subscribers import (
            THUMBNAIL_CLEANUP_SUBSCRIBER_ID,
            THUMBNAIL_GENERATE_SUBSCRIBER_ID,
            cleanup_activity_thumbnail_for_event,
            generate_activity_thumbnail_for_event,
            register_thumbnail_durable_handlers,
        )
        from core.jobs.registry import JobHandlerRegistry

        registry = JobHandlerRegistry()
        register_thumbnail_durable_handlers(registry)

        assert registry.get(THUMBNAIL_GENERATE_SUBSCRIBER_ID) is generate_activity_thumbnail_for_event
        assert registry.get(THUMBNAIL_CLEANUP_SUBSCRIBER_ID) is cleanup_activity_thumbnail_for_event
        assert registry.subscribers_for("activity.created") == (THUMBNAIL_GENERATE_SUBSCRIBER_ID,)
        assert registry.subscribers_for("activity.deleted") == (THUMBNAIL_CLEANUP_SUBSCRIBER_ID,)
