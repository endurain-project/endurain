"""Tests for accepting, running and pruning activity upload jobs."""

from datetime import UTC, datetime
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
            patch.object(upload_jobs.upload_entry, "stage_uploaded_activity_file", return_value="abc.gpx"),
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
        # The payload carries only the job id: the key and owner are columns.
        assert publish.call_args.args[1] == {"job_id": create.call_args.args[0]}
        submit.assert_not_called()

    def test_falls_back_to_the_background_pool_when_jobs_disabled(self):
        db = MagicMock()
        with (
            patch.object(upload_jobs.core_config.settings, "JOBS_ENABLED", False),
            patch.object(upload_jobs.upload_entry, "stage_uploaded_activity_file", return_value="abc.gpx"),
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

    def test_the_staged_blob_is_discarded_when_queueing_fails(self):
        """Otherwise the blob would sit in storage forever with nothing to consume it."""
        db = MagicMock()
        with (
            patch.object(upload_jobs.core_config.settings, "JOBS_ENABLED", True),
            patch.object(upload_jobs.upload_entry, "stage_uploaded_activity_file", return_value="abc.gpx"),
            patch.object(upload_jobs.upload_crud, "create_upload_job"),
            patch.object(
                upload_jobs.platform_publisher,
                "publish_committing",
                side_effect=RuntimeError("outbox down"),
            ),
            patch.object(upload_jobs.upload_entry, "discard_staged_upload") as discard,
            pytest.raises(RuntimeError),
        ):
            upload_jobs.accept_upload(7, _file(), db)

        discard.assert_called_once_with("abc.gpx")


class TestRunUploadJob:
    def test_marks_completed_with_the_created_activity_ids(self):
        created = [MagicMock(id=11), MagicMock(id=12)]
        with (
            patch.object(upload_jobs.core_database, "SessionLocal") as session_local,
            patch.object(upload_jobs.upload_crud, "get_job_work_item", return_value=(7, "abc.gpx")),
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
            patch.object(upload_jobs.upload_crud, "get_job_work_item", return_value=(7, "abc.gpx")),
            patch.object(upload_jobs.upload_crud, "mark_processing"),
            patch.object(upload_jobs.upload_crud, "mark_failed") as failed,
            patch.object(upload_jobs.upload_entry, "process_staged_upload", return_value=None),
        ):
            session_local.return_value.__enter__.return_value = MagicMock()
            upload_jobs.run_upload_job("job-1")

        assert failed.call_args.args[1] == activity_ingestion_schema.UploadJobErrorCode.NO_ACTIVITIES_FOUND

    def test_a_rejected_file_is_terminal_immediately(self):
        """The same file fails identically on every retry, so don't burn attempts."""
        with (
            patch.object(upload_jobs.core_config.settings, "JOBS_ENABLED", True),
            patch.object(upload_jobs.core_database, "SessionLocal") as session_local,
            patch.object(upload_jobs.upload_crud, "get_job_work_item", return_value=(7, "abc.gz")),
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
        assert fail.call_args.args[2] == "abc.gz"

    def test_a_transient_failure_is_left_for_the_retry(self):
        """Marking it failed here would tell the user a database blip rejected their file."""
        with (
            patch.object(upload_jobs.core_config.settings, "JOBS_ENABLED", True),
            patch.object(upload_jobs.core_database, "SessionLocal") as session_local,
            patch.object(upload_jobs.upload_crud, "get_job_work_item", return_value=(7, "abc.gpx")),
            patch.object(upload_jobs.upload_crud, "mark_processing"),
            patch.object(upload_jobs, "fail_upload_job") as fail,
            patch.object(
                upload_jobs.upload_entry,
                "process_staged_upload",
                side_effect=core_exceptions.ProcessingError(),
            ),
            pytest.raises(core_exceptions.ProcessingError),
        ):
            session_local.return_value.__enter__.return_value = MagicMock()
            upload_jobs.run_upload_job("job-1")

        fail.assert_not_called()

    def test_a_transient_failure_is_terminal_when_nothing_will_retry(self):
        """The fallback pool runs each job once, so waiting for a retry would hang the poller."""
        with (
            patch.object(upload_jobs.core_config.settings, "JOBS_ENABLED", False),
            patch.object(upload_jobs.core_database, "SessionLocal") as session_local,
            patch.object(upload_jobs.upload_crud, "get_job_work_item", return_value=(7, "abc.gpx")),
            patch.object(upload_jobs.upload_crud, "mark_processing"),
            patch.object(upload_jobs, "fail_upload_job") as fail,
            patch.object(
                upload_jobs.upload_entry,
                "process_staged_upload",
                side_effect=core_exceptions.ProcessingError(),
            ),
            pytest.raises(core_exceptions.ProcessingError),
        ):
            session_local.return_value.__enter__.return_value = MagicMock()
            upload_jobs.run_upload_job("job-1")

        assert fail.call_args.args[1] == activity_ingestion_schema.UploadJobErrorCode.PROCESSING_FAILED


class TestFailUploadJob:
    def test_discards_the_blob_after_the_row_is_terminal(self):
        with (
            patch.object(upload_jobs.core_database, "SessionLocal") as session_local,
            patch.object(upload_jobs.upload_crud, "mark_failed") as failed,
            patch.object(upload_jobs.upload_entry, "discard_staged_upload") as discard,
        ):
            session_local.return_value.__enter__.return_value = MagicMock()
            upload_jobs.fail_upload_job(
                "job-1",
                activity_ingestion_schema.UploadJobErrorCode.PROCESSING_FAILED,
                "abc.gpx",
            )

        failed.assert_called_once()
        discard.assert_called_once_with("abc.gpx")

    def test_looks_the_key_up_when_the_caller_does_not_have_it(self):
        """The dead-letter path only knows the job id."""
        with (
            patch.object(upload_jobs.core_database, "SessionLocal") as session_local,
            patch.object(upload_jobs.upload_crud, "get_job_work_item", return_value=(7, "abc.gpx")),
            patch.object(upload_jobs.upload_crud, "mark_failed"),
            patch.object(upload_jobs.upload_entry, "discard_staged_upload") as discard,
        ):
            session_local.return_value.__enter__.return_value = MagicMock()
            upload_jobs.fail_upload_job("job-1", activity_ingestion_schema.UploadJobErrorCode.PROCESSING_FAILED)

        discard.assert_called_once_with("abc.gpx")

    def test_a_bookkeeping_failure_never_propagates(self):
        """It must not mask the original import failure."""
        with (
            patch.object(upload_jobs.core_database, "SessionLocal", side_effect=RuntimeError("db down")),
            patch.object(upload_jobs.upload_entry, "discard_staged_upload"),
        ):
            upload_jobs.fail_upload_job(
                "job-1",
                activity_ingestion_schema.UploadJobErrorCode.PROCESSING_FAILED,
                "abc.gpx",
            )


class TestPruneExpiredUploadJobs:
    def _platform(self, acquired: bool = True) -> MagicMock:
        platform = MagicMock()
        platform.lock.try_acquire.return_value.__enter__.return_value = acquired
        platform.clock.now.return_value = datetime(2026, 7, 28, tzinfo=UTC)
        return platform

    def test_deletes_finished_jobs_past_the_window(self):
        with (
            patch.object(upload_jobs.core_config.settings, "JOBS_RETENTION_DAYS", 90),
            patch.object(upload_jobs.platform_runtime, "get_active_platform", return_value=self._platform()),
            patch.object(upload_jobs.core_database, "SessionLocal") as session_local,
            patch.object(upload_jobs.upload_crud, "delete_jobs_before", return_value=3) as delete,
        ):
            session_local.return_value.__enter__.return_value = MagicMock()
            upload_jobs.prune_expired_upload_jobs()

        # The cutoff is the window applied to the platform clock, not wall time.
        assert delete.call_args.args[0] == datetime(2026, 4, 29, tzinfo=UTC)

    def test_is_inert_when_retention_is_disabled(self):
        with (
            patch.object(upload_jobs.core_config.settings, "JOBS_RETENTION_DAYS", 0),
            patch.object(upload_jobs.platform_runtime, "get_active_platform") as platform,
        ):
            upload_jobs.prune_expired_upload_jobs()

        platform.assert_not_called()

    def test_skips_when_another_replica_holds_the_lock(self):
        with (
            patch.object(upload_jobs.core_config.settings, "JOBS_RETENTION_DAYS", 90),
            patch.object(
                upload_jobs.platform_runtime,
                "get_active_platform",
                return_value=self._platform(acquired=False),
            ),
            patch.object(upload_jobs.upload_crud, "delete_jobs_before") as delete,
        ):
            upload_jobs.prune_expired_upload_jobs()

        delete.assert_not_called()


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
