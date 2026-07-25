"""Tests for the platform publish facade."""

from unittest.mock import MagicMock, patch


class TestPublish:
    @patch("infra.publisher.core_middleware_request_id")
    @patch("infra.publisher.platform_runtime")
    def test_publishes_event_with_payload_and_metadata(self, mock_runtime, mock_req_id):
        from infra.publisher import publish

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

    @patch("infra.publisher.core_middleware_request_id")
    @patch("infra.publisher.platform_runtime")
    def test_injects_ambient_request_id(self, mock_runtime, mock_req_id):
        from infra.publisher import publish

        platform = MagicMock()
        mock_runtime.get_active_platform.return_value = platform
        mock_req_id.get_request_id.return_value = "req-123"

        publish("activity.created", {"activity_id": 1}, source="api:test", metadata={"user_id": 3})

        event = platform.events.publish.call_args.args[0]
        assert event.metadata == {"request_id": "req-123", "user_id": 3}

    @patch("infra.publisher.core_logger")
    @patch("infra.publisher.platform_runtime")
    def test_swallows_and_logs_when_platform_unavailable(self, mock_runtime, mock_logger):
        from infra.publisher import publish

        mock_runtime.get_active_platform.side_effect = RuntimeError("no platform")

        # Must not raise — publishing is best-effort so it never breaks the producer.
        publish("activity.created", {"activity_id": 1}, source="api:test")

        mock_logger.print_to_log.assert_called()


class TestDurableRouting:
    @patch("infra.publisher.jobs_outbox")
    @patch("infra.publisher.jobs_registry")
    @patch("infra.publisher.core_config")
    @patch("infra.publisher.core_middleware_request_id")
    @patch("infra.publisher.platform_runtime")
    def test_writes_to_outbox_when_durable(self, mock_runtime, mock_req_id, mock_config, mock_registry, mock_outbox):
        from infra.publisher import publish

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

    @patch("infra.publisher.jobs_outbox")
    @patch("infra.publisher.jobs_registry")
    @patch("infra.publisher.core_config")
    @patch("infra.publisher.core_middleware_request_id")
    @patch("infra.publisher.platform_runtime")
    def test_durable_path_tolerates_no_recorder(
        self, mock_runtime, mock_req_id, mock_config, mock_registry, mock_outbox
    ):
        from infra.publisher import publish

        platform = MagicMock()
        platform.recorder = None  # event logging disabled
        mock_runtime.get_active_platform.return_value = platform
        mock_req_id.get_request_id.return_value = ""
        mock_config.settings.JOBS_ENABLED = True
        mock_registry.registry.subscribers_for.return_value = ("thumb.generate",)

        publish("activity.created", {"activity_id": 1}, source="api:test", db=MagicMock())

        mock_outbox.add_to_outbox.assert_called_once()

    @patch("infra.publisher.jobs_outbox")
    @patch("infra.publisher.jobs_registry")
    @patch("infra.publisher.core_config")
    @patch("infra.publisher.core_middleware_request_id")
    @patch("infra.publisher.platform_runtime")
    def test_uses_bus_when_no_db(self, mock_runtime, mock_req_id, mock_config, mock_registry, mock_outbox):
        from infra.publisher import publish

        platform = MagicMock()
        mock_runtime.get_active_platform.return_value = platform
        mock_req_id.get_request_id.return_value = ""
        mock_config.settings.JOBS_ENABLED = True
        mock_registry.registry.subscribers_for.return_value = ("thumb.generate",)

        publish("activity.created", {"activity_id": 1}, source="api:test")  # no db

        mock_outbox.add_to_outbox.assert_not_called()
        platform.events.publish.assert_called_once()

    @patch("infra.publisher.jobs_outbox")
    @patch("infra.publisher.jobs_registry")
    @patch("infra.publisher.core_config")
    @patch("infra.publisher.core_middleware_request_id")
    @patch("infra.publisher.platform_runtime")
    def test_uses_bus_when_no_durable_subscribers(
        self, mock_runtime, mock_req_id, mock_config, mock_registry, mock_outbox
    ):
        from infra.publisher import publish

        platform = MagicMock()
        mock_runtime.get_active_platform.return_value = platform
        mock_req_id.get_request_id.return_value = ""
        mock_config.settings.JOBS_ENABLED = True
        mock_registry.registry.subscribers_for.return_value = ()

        publish("activity.created", {"activity_id": 1}, source="api:test", db=MagicMock())

        mock_outbox.add_to_outbox.assert_not_called()
        platform.events.publish.assert_called_once()

    @patch("infra.publisher.jobs_outbox")
    @patch("infra.publisher.jobs_registry")
    @patch("infra.publisher.core_config")
    @patch("infra.publisher.core_middleware_request_id")
    @patch("infra.publisher.platform_runtime")
    def test_uses_bus_when_jobs_disabled(self, mock_runtime, mock_req_id, mock_config, mock_registry, mock_outbox):
        from infra.publisher import publish

        platform = MagicMock()
        mock_runtime.get_active_platform.return_value = platform
        mock_req_id.get_request_id.return_value = ""
        mock_config.settings.JOBS_ENABLED = False
        mock_registry.registry.subscribers_for.return_value = ("thumb.generate",)

        publish("activity.created", {"activity_id": 1}, source="api:test", db=MagicMock())

        mock_outbox.add_to_outbox.assert_not_called()
        platform.events.publish.assert_called_once()


class TestPublishManyCommitting:
    """Batch counterpart of publish_committing, for bulk deletes / bulk enqueues.

    The point is one commit for the whole batch (not one per event) and, on the
    durable path, propagating staging failures instead of swallowing them.
    """

    @patch("infra.publisher.jobs_outbox")
    @patch("infra.publisher.jobs_registry")
    @patch("infra.publisher.core_config")
    @patch("infra.publisher.core_middleware_request_id")
    @patch("infra.publisher.platform_runtime")
    def test_stages_all_events_then_commits_once(
        self, mock_runtime, mock_req_id, mock_config, mock_registry, mock_outbox
    ):
        from infra.publisher import publish_many_committing

        mock_runtime.get_active_platform.return_value = MagicMock()
        mock_req_id.get_request_id.return_value = ""
        mock_config.settings.JOBS_ENABLED = True
        mock_registry.registry.subscribers_for.return_value = ("thumb.cleanup",)
        commit = MagicMock()

        publish_many_committing(
            "activity.deleted",
            [{"activity_id": 1}, {"activity_id": 2}, {"activity_id": 3}],
            source="api:test",
            db=MagicMock(),
            commit=commit,
        )

        assert mock_outbox.add_to_outbox.call_count == 3
        # Every row is staged uncommitted so it joins the caller's transaction.
        for call in mock_outbox.add_to_outbox.call_args_list:
            assert call.kwargs["commit"] is False
        commit.assert_called_once()

    @patch("infra.publisher.jobs_outbox")
    @patch("infra.publisher.jobs_registry")
    @patch("infra.publisher.core_config")
    @patch("infra.publisher.core_middleware_request_id")
    @patch("infra.publisher.platform_runtime")
    def test_applies_per_payload_metadata(self, mock_runtime, mock_req_id, mock_config, mock_registry, mock_outbox):
        from infra.publisher import publish_many_committing

        mock_runtime.get_active_platform.return_value = MagicMock()
        mock_req_id.get_request_id.return_value = ""
        mock_config.settings.JOBS_ENABLED = True
        mock_registry.registry.subscribers_for.return_value = ("thumb.cleanup",)

        publish_many_committing(
            "activity.deleted",
            [{"activity_id": 1}, {"activity_id": 2}],
            source="api:test",
            metadata_for=lambda payload: {"activity_id": payload["activity_id"], "user_id": 9},
            db=MagicMock(),
            commit=MagicMock(),
        )

        staged = [call.args[0] for call in mock_outbox.add_to_outbox.call_args_list]
        assert [event.metadata["activity_id"] for event in staged] == [1, 2]
        assert all(event.metadata["user_id"] == 9 for event in staged)

    @patch("infra.publisher.jobs_outbox")
    @patch("infra.publisher.jobs_registry")
    @patch("infra.publisher.core_config")
    @patch("infra.publisher.core_middleware_request_id")
    @patch("infra.publisher.platform_runtime")
    def test_staging_failure_propagates_and_skips_commit(
        self, mock_runtime, mock_req_id, mock_config, mock_registry, mock_outbox
    ):
        """A failed stage must not commit — the caller rolls the whole unit back."""
        import pytest

        from infra.publisher import publish_many_committing

        mock_runtime.get_active_platform.return_value = MagicMock()
        mock_req_id.get_request_id.return_value = ""
        mock_config.settings.JOBS_ENABLED = True
        mock_registry.registry.subscribers_for.return_value = ("thumb.cleanup",)
        mock_outbox.add_to_outbox.side_effect = RuntimeError("outbox down")
        commit = MagicMock()

        with pytest.raises(RuntimeError):
            publish_many_committing(
                "activity.deleted",
                [{"activity_id": 1}],
                source="api:test",
                db=MagicMock(),
                commit=commit,
            )

        commit.assert_not_called()

    @patch("infra.publisher.jobs_outbox")
    @patch("infra.publisher.jobs_registry")
    @patch("infra.publisher.core_config")
    @patch("infra.publisher.core_middleware_request_id")
    @patch("infra.publisher.platform_runtime")
    def test_best_effort_path_commits_first_then_dispatches(
        self, mock_runtime, mock_req_id, mock_config, mock_registry, mock_outbox
    ):
        from infra.publisher import publish_many_committing

        platform = MagicMock()
        mock_runtime.get_active_platform.return_value = platform
        mock_req_id.get_request_id.return_value = ""
        mock_config.settings.JOBS_ENABLED = False
        mock_registry.registry.subscribers_for.return_value = ()
        commit = MagicMock()

        publish_many_committing(
            "activity.deleted",
            [{"activity_id": 1}, {"activity_id": 2}],
            source="api:test",
            db=MagicMock(),
            commit=commit,
        )

        commit.assert_called_once()
        mock_outbox.add_to_outbox.assert_not_called()
        assert platform.events.publish.call_count == 2

    @patch("infra.publisher.jobs_outbox")
    @patch("infra.publisher.jobs_registry")
    @patch("infra.publisher.core_config")
    @patch("infra.publisher.core_middleware_request_id")
    @patch("infra.publisher.platform_runtime")
    def test_empty_batch_still_commits_once(self, mock_runtime, mock_req_id, mock_config, mock_registry, mock_outbox):
        from infra.publisher import publish_many_committing

        mock_runtime.get_active_platform.return_value = MagicMock()
        mock_req_id.get_request_id.return_value = ""
        mock_config.settings.JOBS_ENABLED = True
        mock_registry.registry.subscribers_for.return_value = ("thumb.cleanup",)
        commit = MagicMock()

        publish_many_committing("activity.deleted", [], source="api:test", db=MagicMock(), commit=commit)

        mock_outbox.add_to_outbox.assert_not_called()
        commit.assert_called_once()
