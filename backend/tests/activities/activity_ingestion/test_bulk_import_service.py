"""Tests for starting a bulk import: scanning, validating and queuing.

The route used to hold this branching inline; it now delegates, so the behaviour
is exercised where it lives.
"""

from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy.exc import SQLAlchemyError

import core.exceptions as core_exceptions
import modules.activities.activity_ingestion.bulk_import_service as bulk_import_service


class TestStartBulkImport:
    def test_enqueues_one_durable_job_per_file_when_jobs_enabled(self):
        db = MagicMock()
        with (
            patch.object(bulk_import_service.core_config.settings, "JOBS_ENABLED", True),
            patch.object(bulk_import_service.os, "makedirs"),
            patch.object(bulk_import_service.os, "listdir", return_value=["a.gpx", "b.fit"]),
            patch.object(bulk_import_service.os.path, "isfile", return_value=True),
            patch.object(bulk_import_service.core_file_uploads, "validate_local_file_sync"),
            patch.object(bulk_import_service.activity_bulk_import_subscribers, "publish_bulk_import_files") as publish,
            patch.object(bulk_import_service.activity_ingestion_background, "submit_bulk_import") as submit,
        ):
            result = bulk_import_service.start_bulk_import(3, db)

        assert result == 2
        # One batched publish for every file, staged in a single transaction.
        publish.assert_called_once()
        assert len(publish.call_args.args[0]) == 2
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
            patch.object(bulk_import_service.activity_bulk_import_subscribers, "publish_bulk_import_files") as publish,
            patch.object(bulk_import_service.activity_ingestion_background, "submit_bulk_import") as submit,
        ):
            result = bulk_import_service.start_bulk_import(3, db)

        assert result == 1
        publish.assert_not_called()
        submit.assert_called_once()

    def test_skips_unsupported_extensions(self):
        db = MagicMock()
        with (
            patch.object(bulk_import_service.core_config.settings, "JOBS_ENABLED", True),
            patch.object(bulk_import_service.os, "makedirs"),
            patch.object(bulk_import_service.os, "listdir", return_value=["notes.txt"]),
            patch.object(bulk_import_service.os.path, "isfile", return_value=True),
            patch.object(bulk_import_service.core_file_uploads, "validate_local_file_sync"),
            patch.object(bulk_import_service.activity_bulk_import_subscribers, "publish_bulk_import_files") as publish,
            patch.object(bulk_import_service.activity_ingestion_background, "submit_bulk_import"),
        ):
            bulk_import_service.start_bulk_import(3, db)

        # Nothing valid to queue -> an empty batch is still published so the
        # request commits exactly once either way.
        assert publish.call_args.args[0] == []
