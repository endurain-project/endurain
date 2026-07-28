"""Tests for the durable uploaded-file subscriber."""

from unittest.mock import patch

import pytest
from pydantic import ValidationError

import modules.activities.activity_ingestion.events as ingestion_events
import modules.activities.activity_ingestion.schema as activity_ingestion_schema
import modules.activities.activity_ingestion.upload_subscribers as upload_subscribers
from infra.events import Event
from infra.jobs.registry import JobHandlerRegistry


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


class TestProcessUploadedFileForEvent:
    def test_runs_the_upload_job(self):
        with patch.object(upload_subscribers.upload_jobs, "run_upload_job") as run:
            upload_subscribers.process_uploaded_file_for_event(_event({"job_id": "job-1"}))
        run.assert_called_once_with("job-1")

    def test_raises_on_a_malformed_payload(self):
        """A bad payload must surface via retry/dead-letter, not silently complete."""
        with pytest.raises(ValidationError):
            upload_subscribers.process_uploaded_file_for_event(_event({}))

    def test_a_retryable_failure_leaves_the_job_alone(self):
        with (
            patch.object(upload_subscribers.core_config.settings, "JOBS_MAX_ATTEMPTS", 5),
            patch.object(upload_subscribers.upload_jobs, "run_upload_job", side_effect=RuntimeError("db blip")),
            patch.object(upload_subscribers.upload_jobs, "fail_upload_job") as fail,
            pytest.raises(RuntimeError),
        ):
            upload_subscribers.process_uploaded_file_for_event(_event({"job_id": "job-1"}, retry_count=1))

        # Attempts remain, so the uploader is not told their file was rejected
        # because of a transient error.
        fail.assert_not_called()

    def test_the_final_attempt_gives_the_uploader_a_terminal_status(self):
        with (
            patch.object(upload_subscribers.core_config.settings, "JOBS_MAX_ATTEMPTS", 5),
            patch.object(upload_subscribers.upload_jobs, "run_upload_job", side_effect=RuntimeError("still broken")),
            patch.object(upload_subscribers.upload_jobs, "fail_upload_job") as fail,
            pytest.raises(RuntimeError),
        ):
            upload_subscribers.process_uploaded_file_for_event(_event({"job_id": "job-1"}, retry_count=5))

        # Otherwise a dead-lettered upload would sit at "processing" forever.
        fail.assert_called_once_with("job-1", activity_ingestion_schema.UploadJobErrorCode.PROCESSING_FAILED)


class TestRegisterUploadDurableHandlers:
    def test_registers_the_handler(self):
        registry = JobHandlerRegistry()
        upload_subscribers.register_upload_durable_handlers(registry)
        assert tuple(registry.subscribers_for(ingestion_events.ACTIVITY_FILE_UPLOADED)) == (
            upload_subscribers.UPLOADED_FILE_SUBSCRIBER_ID,
        )
        assert registry.get(upload_subscribers.UPLOADED_FILE_SUBSCRIBER_ID) is not None
