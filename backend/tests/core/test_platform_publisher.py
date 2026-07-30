"""Tests for the platform publish facade."""

from unittest.mock import MagicMock, patch


class TestPublish:
    @patch("core.platform.publisher.core_middleware_request_id")
    @patch("core.platform.publisher.platform_runtime")
    def test_publishes_event_with_payload_and_metadata(self, mock_runtime, mock_req_id):
        from core.platform.publisher import publish

        platform = MagicMock()
        mock_runtime.get_active_platform.return_value = platform
        mock_req_id.get_request_id.return_value = ""

        publish("activity.created", {"activity_id": 1}, source="api:test", metadata={"user_id": 3})

        platform.events.publish.assert_called_once()
        event = platform.events.publish.call_args.args[0]
        assert event.event_type == "activity.created"
        assert event.payload == {"activity_id": 1}
        assert event.source == "api:test"
        assert event.metadata["user_id"] == 3
        # No ambient request id, so the key is absent (not an empty string).
        assert "request_id" not in event.metadata

    @patch("core.platform.publisher.core_middleware_request_id")
    @patch("core.platform.publisher.platform_runtime")
    def test_injects_ambient_request_id(self, mock_runtime, mock_req_id):
        from core.platform.publisher import publish

        platform = MagicMock()
        mock_runtime.get_active_platform.return_value = platform
        mock_req_id.get_request_id.return_value = "req-123"

        publish("activity.created", {"activity_id": 1}, source="api:test", metadata={"user_id": 3})

        event = platform.events.publish.call_args.args[0]
        assert event.metadata == {"request_id": "req-123", "user_id": 3}

    @patch("core.platform.publisher.core_logger")
    @patch("core.platform.publisher.platform_runtime")
    def test_swallows_and_logs_when_platform_unavailable(self, mock_runtime, mock_logger):
        from core.platform.publisher import publish

        mock_runtime.get_active_platform.side_effect = RuntimeError("no platform")

        # Must not raise — publishing is best-effort so it never breaks the producer.
        publish("activity.created", {"activity_id": 1}, source="api:test")

        mock_logger.print_to_log.assert_called()


class TestDurableRouting:
    @patch("core.platform.publisher.jobs_outbox")
    @patch("core.platform.publisher.jobs_registry")
    @patch("core.platform.publisher.core_config")
    @patch("core.platform.publisher.core_middleware_request_id")
    @patch("core.platform.publisher.platform_runtime")
    def test_writes_to_outbox_when_durable(self, mock_runtime, mock_req_id, mock_config, mock_registry, mock_outbox):
        from core.platform.publisher import publish

        platform = MagicMock()
        mock_runtime.get_active_platform.return_value = platform
        mock_req_id.get_request_id.return_value = ""
        mock_config.settings.JOBS_ENABLED = True
        mock_registry.registry.subscribers_for.return_value = ("thumb.generate",)
        db = MagicMock()

        publish("activity.created", {"activity_id": 1}, source="api:test", db=db)

        mock_outbox.add_to_outbox.assert_called_once()
        assert mock_outbox.add_to_outbox.call_args.kwargs["db"] is db
        platform.events.publish.assert_not_called()
        # Durable events are recorded 'queued' so event_log isn't dark.
        platform.recorder.record_queued.assert_called_once()

    @patch("core.platform.publisher.jobs_outbox")
    @patch("core.platform.publisher.jobs_registry")
    @patch("core.platform.publisher.core_config")
    @patch("core.platform.publisher.core_middleware_request_id")
    @patch("core.platform.publisher.platform_runtime")
    def test_durable_path_tolerates_no_recorder(
        self, mock_runtime, mock_req_id, mock_config, mock_registry, mock_outbox
    ):
        from core.platform.publisher import publish

        platform = MagicMock()
        platform.recorder = None  # event logging disabled
        mock_runtime.get_active_platform.return_value = platform
        mock_req_id.get_request_id.return_value = ""
        mock_config.settings.JOBS_ENABLED = True
        mock_registry.registry.subscribers_for.return_value = ("thumb.generate",)

        publish("activity.created", {"activity_id": 1}, source="api:test", db=MagicMock())

        mock_outbox.add_to_outbox.assert_called_once()

    @patch("core.platform.publisher.jobs_outbox")
    @patch("core.platform.publisher.jobs_registry")
    @patch("core.platform.publisher.core_config")
    @patch("core.platform.publisher.core_middleware_request_id")
    @patch("core.platform.publisher.platform_runtime")
    def test_uses_bus_when_no_db(self, mock_runtime, mock_req_id, mock_config, mock_registry, mock_outbox):
        from core.platform.publisher import publish

        platform = MagicMock()
        mock_runtime.get_active_platform.return_value = platform
        mock_req_id.get_request_id.return_value = ""
        mock_config.settings.JOBS_ENABLED = True
        mock_registry.registry.subscribers_for.return_value = ("thumb.generate",)

        publish("activity.created", {"activity_id": 1}, source="api:test")  # no db

        mock_outbox.add_to_outbox.assert_not_called()
        platform.events.publish.assert_called_once()

    @patch("core.platform.publisher.jobs_outbox")
    @patch("core.platform.publisher.jobs_registry")
    @patch("core.platform.publisher.core_config")
    @patch("core.platform.publisher.core_middleware_request_id")
    @patch("core.platform.publisher.platform_runtime")
    def test_uses_bus_when_no_durable_subscribers(
        self, mock_runtime, mock_req_id, mock_config, mock_registry, mock_outbox
    ):
        from core.platform.publisher import publish

        platform = MagicMock()
        mock_runtime.get_active_platform.return_value = platform
        mock_req_id.get_request_id.return_value = ""
        mock_config.settings.JOBS_ENABLED = True
        mock_registry.registry.subscribers_for.return_value = ()

        publish("activity.created", {"activity_id": 1}, source="api:test", db=MagicMock())

        mock_outbox.add_to_outbox.assert_not_called()
        platform.events.publish.assert_called_once()

    @patch("core.platform.publisher.jobs_outbox")
    @patch("core.platform.publisher.jobs_registry")
    @patch("core.platform.publisher.core_config")
    @patch("core.platform.publisher.core_middleware_request_id")
    @patch("core.platform.publisher.platform_runtime")
    def test_uses_bus_when_jobs_disabled(self, mock_runtime, mock_req_id, mock_config, mock_registry, mock_outbox):
        from core.platform.publisher import publish

        platform = MagicMock()
        mock_runtime.get_active_platform.return_value = platform
        mock_req_id.get_request_id.return_value = ""
        mock_config.settings.JOBS_ENABLED = False
        mock_registry.registry.subscribers_for.return_value = ("thumb.generate",)

        publish("activity.created", {"activity_id": 1}, source="api:test", db=MagicMock())

        mock_outbox.add_to_outbox.assert_not_called()
        platform.events.publish.assert_called_once()
