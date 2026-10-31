"""Tests for the durable uploaded-file subscriber."""

from unittest.mock import patch

import pytest
from jasil.events import Event
from jasil.jobs.registry import JobHandlerRegistry
from pydantic import ValidationError

import modules.activities.activity_ingestion.constants as activity_ingestion_constants
import modules.activities.activity_ingestion.events as ingestion_events
import modules.activities.activity_ingestion.subscribers as ingestion_subscribers


def _event(payload: dict, retry_count: int = 1) -> Event:
    return Event(
        event_id="evt-1",
        event_type=ingestion_events.ACTIVITY_FILE_UPLOADED,
        source="api:upload",
        timestamp="2026-07-28T00:00:00+00:00",
        payload=payload,
        metadata={},
        retry_count=retry_count,
    )


@pytest.fixture(autouse=True)
def platform():
    """Resolve the provider from a stand-in so no runtime has to be active."""
    with patch.object(ingestion_subscribers.platform_runtime, "get_active_platform") as get:
        yield get.return_value


class TestProcessUploadedFileForEvent:
    def test_runs_the_upload_job(self, platform):
        with patch.object(ingestion_subscribers.activity_ingestion_service, "run_upload_job") as run:
            ingestion_subscribers.process_uploaded_file_for_event(_event({"job_id": "job-1"}))
        run.assert_called_once_with("job-1", platform.storage)

    def test_raises_on_a_malformed_payload(self):
        """A bad payload must surface via retry/dead-letter, not silently complete."""
        with pytest.raises(ValidationError):
            ingestion_subscribers.process_uploaded_file_for_event(_event({}))

    def test_a_retryable_failure_leaves_the_job_alone(self):
        with (
            patch.object(ingestion_subscribers.core_config.settings, "JOBS_MAX_ATTEMPTS", 5),
            patch.object(
                ingestion_subscribers.activity_ingestion_service, "run_upload_job", side_effect=RuntimeError("db blip")
            ),
            patch.object(ingestion_subscribers.activity_ingestion_service, "fail_ingestion_job") as fail,
            pytest.raises(RuntimeError),
        ):
            ingestion_subscribers.process_uploaded_file_for_event(_event({"job_id": "job-1"}, retry_count=1))

        # Attempts remain, so the uploader is not told their file was rejected
        # because of a transient error.
        fail.assert_not_called()

    def test_the_final_attempt_gives_the_uploader_a_terminal_status(self, platform):
        with (
            patch.object(ingestion_subscribers.core_config.settings, "JOBS_MAX_ATTEMPTS", 5),
            patch.object(
                ingestion_subscribers.activity_ingestion_service,
                "run_upload_job",
                side_effect=RuntimeError("still broken"),
            ),
            patch.object(ingestion_subscribers.activity_ingestion_service, "fail_ingestion_job") as fail,
            pytest.raises(RuntimeError),
        ):
            ingestion_subscribers.process_uploaded_file_for_event(_event({"job_id": "job-1"}, retry_count=5))

        # Otherwise a dead-lettered upload would sit at "processing" forever.
        fail.assert_called_once_with(
            "job-1", activity_ingestion_constants.IngestionJobErrorCode.PROCESSING_FAILED, platform.storage
        )


class TestRegisterUploadDurableHandlers:
    def test_registers_the_handler(self):
        registry = JobHandlerRegistry()
        ingestion_subscribers.register_durable_handlers(registry)
        assert tuple(registry.subscribers_for(ingestion_events.ACTIVITY_FILE_UPLOADED)) == (
            ingestion_subscribers.UPLOADED_FILE_SUBSCRIBER_ID,
        )
        assert registry.get(ingestion_subscribers.UPLOADED_FILE_SUBSCRIBER_ID) is not None


class TestBulkImportHandler:
    """The durable handler for one batch of a bulk import."""

    def _event(self, retry_count: int = 1) -> Event:
        return Event(
            event_id="evt-1",
            event_type=ingestion_events.ACTIVITY_BULK_IMPORT_CONTINUE,
            source="api:bulk_import",
            timestamp="2026-10-15T00:00:00+00:00",
            payload={"job_id": "job-1"},
            metadata={},
            retry_count=retry_count,
        )

    def test_runs_one_batch_for_the_job_named_in_the_event(self):
        from unittest.mock import MagicMock, patch

        import modules.activities.activity_ingestion.subscribers as subscribers

        with (
            patch.object(subscribers.platform_runtime, "get_active_platform") as platform,
            patch.object(subscribers.activity_ingestion_bulk_import_service, "run_bulk_import_job") as run,
        ):
            platform.return_value = MagicMock(storage="storage")
            subscribers.process_bulk_import_for_event(self._event())

        run.assert_called_once_with("job-1", "storage")

    def test_the_final_failed_attempt_closes_the_job_and_reraises(self):
        from unittest.mock import MagicMock, patch

        import pytest

        import modules.activities.activity_ingestion.subscribers as subscribers

        final = subscribers.core_config.settings.JOBS_MAX_ATTEMPTS
        with (
            patch.object(subscribers.platform_runtime, "get_active_platform") as platform,
            patch.object(
                subscribers.activity_ingestion_bulk_import_service, "run_bulk_import_job", side_effect=RuntimeError("x")
            ),
            patch.object(subscribers.activity_ingestion_service, "fail_ingestion_job") as fail,
            pytest.raises(RuntimeError),
        ):
            platform.return_value = MagicMock(storage="storage")
            subscribers.process_bulk_import_for_event(self._event(retry_count=final))

        fail.assert_called_once()

    def test_an_earlier_failure_is_left_to_the_retry(self):
        from unittest.mock import MagicMock, patch

        import pytest

        import modules.activities.activity_ingestion.subscribers as subscribers

        with (
            patch.object(subscribers.platform_runtime, "get_active_platform") as platform,
            patch.object(
                subscribers.activity_ingestion_bulk_import_service, "run_bulk_import_job", side_effect=RuntimeError("x")
            ),
            patch.object(subscribers.activity_ingestion_service, "fail_ingestion_job") as fail,
            pytest.raises(RuntimeError),
        ):
            platform.return_value = MagicMock(storage="storage")
            subscribers.process_bulk_import_for_event(self._event(retry_count=1))

        fail.assert_not_called()
