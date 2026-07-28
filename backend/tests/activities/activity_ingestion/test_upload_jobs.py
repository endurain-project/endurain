"""Tests for accepting and running activity upload jobs."""

from unittest.mock import MagicMock, patch

import pytest

import core.exceptions as core_exceptions
import modules.activities.activity_ingestion.schema as activity_ingestion_schema
import modules.activities.activity_ingestion.upload_jobs as upload_jobs


def _file(filename: str = "ride.gpx") -> MagicMock:
    file = MagicMock()
    file.filename = filename
    return file


class TestAcceptUpload:
    def test_publishes_a_durable_event_when_jobs_enabled(self):
        db = MagicMock()
        with (
            patch.object(upload_jobs.core_config.settings, "JOBS_ENABLED", True),
            patch.object(upload_jobs.upload_entry, "stage_uploaded_activity_file", return_value="/staged/x.gpx"),
            patch.object(upload_jobs.upload_crud, "create_upload_job") as create,
            patch.object(upload_jobs.upload_crud, "get_upload_job", return_value="job-view"),
            patch.object(upload_jobs.platform_publisher, "publish_committing") as publish,
            patch.object(upload_jobs.activity_ingestion_background, "submit_upload") as submit,
        ):
            result = upload_jobs.accept_upload(7, _file(), db)

        assert result == "job-view"
        # The row is staged, not committed, so it lands in the same transaction
        # as the outbox event.
        assert create.call_args.kwargs["commit"] is False
        publish.assert_called_once()
        assert publish.call_args.kwargs["commit"] == db.commit
        # The payload carries only the job id: the path and owner are columns.
        assert publish.call_args.args[1] == {"job_id": create.call_args.args[0]}
        submit.assert_not_called()

    def test_falls_back_to_the_background_pool_when_jobs_disabled(self):
        db = MagicMock()
        with (
            patch.object(upload_jobs.core_config.settings, "JOBS_ENABLED", False),
            patch.object(upload_jobs.upload_entry, "stage_uploaded_activity_file", return_value="/staged/x.gpx"),
            patch.object(upload_jobs.upload_crud, "create_upload_job") as create,
            patch.object(upload_jobs.upload_crud, "get_upload_job", return_value="job-view"),
            patch.object(upload_jobs.platform_publisher, "publish_committing") as publish,
            patch.object(upload_jobs.activity_ingestion_background, "submit_upload") as submit,
        ):
            upload_jobs.accept_upload(7, _file(), db)

        # Same client contract either way — only the executor differs.
        publish.assert_not_called()
        db.commit.assert_called_once()
        submit.assert_called_once_with(create.call_args.args[0])

    def test_a_rejected_file_never_leaves_a_job_behind(self):
        """Staging runs first, so a 4xx cannot create a row nobody will run."""
        db = MagicMock()
        with (
            patch.object(
                upload_jobs.upload_entry,
                "stage_uploaded_activity_file",
                side_effect=core_exceptions.UnsupportedFormatError("nope"),
            ),
            patch.object(upload_jobs.upload_crud, "create_upload_job") as create,
            pytest.raises(core_exceptions.UnsupportedFormatError),
        ):
            upload_jobs.accept_upload(7, _file("ride.txt"), db)

        create.assert_not_called()

    def test_staged_bytes_are_removed_when_queueing_fails(self):
        """Otherwise the file would sit in staging forever with nothing to consume it."""
        db = MagicMock()
        with (
            patch.object(upload_jobs.core_config.settings, "JOBS_ENABLED", True),
            patch.object(upload_jobs.upload_entry, "stage_uploaded_activity_file", return_value="/staged/x.gpx"),
            patch.object(upload_jobs.upload_crud, "create_upload_job"),
            patch.object(
                upload_jobs.platform_publisher,
                "publish_committing",
                side_effect=RuntimeError("outbox down"),
            ),
            patch.object(upload_jobs.core_file_uploads, "remove_files") as remove,
            pytest.raises(RuntimeError),
        ):
            upload_jobs.accept_upload(7, _file(), db)

        remove.assert_called_once_with(["/staged/x.gpx"])


class TestRunUploadJob:
    def test_marks_completed_with_the_created_activity_ids(self):
        created = [MagicMock(id=11), MagicMock(id=12)]
        with (
            patch.object(upload_jobs.core_database, "SessionLocal") as session_local,
            patch.object(upload_jobs.upload_crud, "get_job_work_item", return_value=(7, "/staged/x.gpx")),
            patch.object(upload_jobs.upload_crud, "mark_processing") as processing,
            patch.object(upload_jobs.upload_crud, "mark_completed") as completed,
            patch.object(upload_jobs.upload_entry, "process_staged_upload", return_value=created),
        ):
            session_local.return_value.__enter__.return_value = MagicMock()
            upload_jobs.run_upload_job("job-1")

        processing.assert_called_once()
        assert completed.call_args.args[0] == "job-1"
        assert completed.call_args.args[1] == [11, 12]

    def test_a_consumed_job_is_a_no_op(self):
        """A retry after a successful import must not import the file twice."""
        with (
            patch.object(upload_jobs.core_database, "SessionLocal") as session_local,
            patch.object(upload_jobs.upload_crud, "get_job_work_item", return_value=None),
            patch.object(upload_jobs.upload_entry, "process_staged_upload") as process,
        ):
            session_local.return_value.__enter__.return_value = MagicMock()
            upload_jobs.run_upload_job("job-1")

        process.assert_not_called()

    def test_an_unparseable_file_fails_with_a_specific_code(self):
        with (
            patch.object(upload_jobs.core_database, "SessionLocal") as session_local,
            patch.object(upload_jobs.upload_crud, "get_job_work_item", return_value=(7, "/staged/x.gpx")),
            patch.object(upload_jobs.upload_crud, "mark_processing"),
            patch.object(upload_jobs.upload_crud, "mark_failed") as failed,
            patch.object(upload_jobs.upload_entry, "process_staged_upload", return_value=None),
        ):
            session_local.return_value.__enter__.return_value = MagicMock()
            upload_jobs.run_upload_job("job-1")

        assert failed.call_args.args[1] == activity_ingestion_schema.UploadJobErrorCode.NO_ACTIVITIES_FOUND

    def test_a_rejected_file_is_terminal_and_still_raises(self):
        """The same file fails identically on every retry, so record it now."""
        with (
            patch.object(upload_jobs.core_database, "SessionLocal") as session_local,
            patch.object(upload_jobs.upload_crud, "get_job_work_item", return_value=(7, "/staged/x.gz")),
            patch.object(upload_jobs.upload_crud, "mark_processing"),
            patch.object(upload_jobs, "fail_upload_job") as fail,
            patch.object(
                upload_jobs.upload_entry,
                "process_staged_upload",
                side_effect=core_exceptions.InvalidInputError("bad payload"),
            ),
            pytest.raises(core_exceptions.InvalidInputError),
        ):
            session_local.return_value.__enter__.return_value = MagicMock()
            upload_jobs.run_upload_job("job-1")

        assert fail.call_args.args[1] == activity_ingestion_schema.UploadJobErrorCode.INVALID_FILE


class TestErrorCodeFor:
    @pytest.mark.parametrize(
        ("error", "expected"),
        [
            (
                core_exceptions.UnsupportedFormatError("x"),
                activity_ingestion_schema.UploadJobErrorCode.UNSUPPORTED_FORMAT,
            ),
            (core_exceptions.InvalidInputError("x"), activity_ingestion_schema.UploadJobErrorCode.INVALID_FILE),
            (core_exceptions.ProcessingError(), activity_ingestion_schema.UploadJobErrorCode.PROCESSING_FAILED),
        ],
    )
    def test_maps_known_failures(self, error, expected):
        assert upload_jobs._error_code_for(error) == expected

    def test_an_unexpected_failure_does_not_leak_its_message(self):
        """The exception text can carry paths and parser internals."""
        code = upload_jobs._error_code_for(RuntimeError("/srv/data/activity_files/secret.fit exploded"))
        assert code == activity_ingestion_schema.UploadJobErrorCode.PROCESSING_FAILED
