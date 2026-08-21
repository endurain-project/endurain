"""Tests for starting a bulk import: scanning, validating and queuing.

The route used to hold this branching inline; it now delegates, so the behaviour
is exercised where it lives.
"""

from datetime import UTC, datetime
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy.exc import SQLAlchemyError

import core.exceptions as core_exceptions
import modules.activities.activity_ingestion.bulk_import_service as bulk_import_service
import modules.activities.activity_ingestion.schema as activity_ingestion_schema


def _job(job_id, user_id, kind, db, *, filename=None, commit=True, **_kwargs):
    """Stand in for the CRUD write, returning the row shape it would create."""
    now = datetime.now(UTC)
    return activity_ingestion_schema.ActivityIngestionJob(
        id=job_id,
        kind=kind,
        filename=filename,
        status=activity_ingestion_schema.IngestionJobStatus.PENDING,
        created_at=now,
        updated_at=now,
    )


class TestStartBulkImport:
    def test_enqueues_one_durable_job_per_file_when_jobs_enabled(self):
        db = MagicMock()
        with (
            patch.object(bulk_import_service.core_config.settings, "JOBS_ENABLED", True),
            patch.object(bulk_import_service.os, "makedirs"),
            patch.object(bulk_import_service.os, "listdir", return_value=["a.gpx", "b.fit"]),
            patch.object(bulk_import_service.os.path, "isfile", return_value=True),
            patch.object(bulk_import_service.core_file_uploads, "validate_local_file_sync"),
            patch.object(bulk_import_service.ingestion_jobs_crud, "create_ingestion_job", side_effect=_job),
            patch.object(bulk_import_service.activity_bulk_import_subscribers, "publish_bulk_import_files") as publish,
            patch.object(bulk_import_service.activity_ingestion_background, "submit_bulk_import") as submit,
        ):
            result = bulk_import_service.start_bulk_import(3, db)

        # One pollable handle per file, not one per batch: each file is retried,
        # dead-lettered and completed independently, so there is no shared
        # outcome a batch-level handle could report.
        assert [job.filename for job in result] == ["a.gpx", "b.fit"]
        assert {job.kind for job in result} == {activity_ingestion_schema.IngestionJobKind.BULK_IMPORT}
        # One batched publish for every file, staged in a single transaction.
        publish.assert_called_once()
        assert [job_id for job_id, _path in publish.call_args.args[0]] == [job.id for job in result]
        assert publish.call_args.args[1] == 3
        assert publish.call_args.args[3] is db
        submit.assert_not_called()

    def test_enqueue_failure_surfaces_as_500(self):
        """A failed enqueue must not answer 202 for files that were never queued."""
        db = MagicMock()
        with (
            patch.object(bulk_import_service.core_config.settings, "JOBS_ENABLED", True),
            patch.object(bulk_import_service.os, "makedirs"),
            patch.object(bulk_import_service.os, "listdir", return_value=["a.gpx"]),
            patch.object(bulk_import_service.os.path, "isfile", return_value=True),
            patch.object(bulk_import_service.core_file_uploads, "validate_local_file_sync"),
            patch.object(bulk_import_service.ingestion_jobs_crud, "create_ingestion_job", side_effect=_job),
            patch.object(
                bulk_import_service.activity_bulk_import_subscribers,
                "publish_bulk_import_files",
                side_effect=SQLAlchemyError("outbox down"),
            ),
            patch.object(bulk_import_service.activity_ingestion_background, "submit_bulk_import"),
            pytest.raises(core_exceptions.ProcessingError) as exc,
        ):
            bulk_import_service.start_bulk_import(3, db)

        assert exc.value.status_code == 500

    def test_falls_back_to_threadpool_when_jobs_disabled(self):
        db = MagicMock()
        with (
            patch.object(bulk_import_service.core_config.settings, "JOBS_ENABLED", False),
            patch.object(bulk_import_service.os, "makedirs"),
            patch.object(bulk_import_service.os, "listdir", return_value=["a.gpx"]),
            patch.object(bulk_import_service.os.path, "isfile", return_value=True),
            patch.object(bulk_import_service.core_file_uploads, "validate_local_file_sync"),
            patch.object(bulk_import_service.ingestion_jobs_crud, "create_ingestion_job", side_effect=_job),
            patch.object(bulk_import_service.activity_bulk_import_subscribers, "publish_bulk_import_files") as publish,
            patch.object(bulk_import_service.activity_ingestion_background, "submit_bulk_import") as submit,
        ):
            result = bulk_import_service.start_bulk_import(3, db)

        assert len(result) == 1
        publish.assert_not_called()
        # The fallback executor moves the same rows, so the handle reports the
        # same states whichever executor ran the import.
        assert [job_id for job_id, _path in submit.call_args.args[1]] == [result[0].id]
        # Nothing publishes, so the job rows need their own commit.
        db.commit.assert_called_once()

    def test_skips_unsupported_extensions(self):
        db = MagicMock()
        with (
            patch.object(bulk_import_service.core_config.settings, "JOBS_ENABLED", True),
            patch.object(bulk_import_service.os, "makedirs"),
            patch.object(bulk_import_service.os, "listdir", return_value=["notes.txt"]),
            patch.object(bulk_import_service.os.path, "isfile", return_value=True),
            patch.object(bulk_import_service.core_file_uploads, "validate_local_file_sync"),
            patch.object(bulk_import_service.ingestion_jobs_crud, "create_ingestion_job", side_effect=_job),
            patch.object(bulk_import_service.activity_bulk_import_subscribers, "publish_bulk_import_files") as publish,
            patch.object(bulk_import_service.activity_ingestion_background, "submit_bulk_import"),
        ):
            assert bulk_import_service.start_bulk_import(3, db) == []

        # Nothing valid to queue -> an empty batch is still published so the
        # request commits exactly once either way.
        assert publish.call_args.args[0] == []
