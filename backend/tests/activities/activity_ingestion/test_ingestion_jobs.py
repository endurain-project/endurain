"""Tests for accepting, running and pruning activity upload jobs."""

from datetime import UTC, datetime
from unittest.mock import ANY, MagicMock, patch

import pytest

import core.exceptions as core_exceptions
import modules.activities.activity_ingestion.constants as activity_ingestion_constants
import modules.activities.activity_ingestion.events as ingestion_events
import modules.activities.activity_ingestion.service as ingestion_jobs
import modules.activities.activity_ingestion.upload_entry_service as upload_entry_service


def _received(fingerprint: str = "abc123") -> upload_entry_service.ReceivedUpload:
    """A received upload, already validated and on local disk."""
    return upload_entry_service.ReceivedUpload(
        incoming_path="/incoming/x.gpx", storage_key="abc.gpx", fingerprint=fingerprint
    )


def _upload(filename: str = "ride.gpx") -> tuple[str, MagicMock]:
    """The client filename and the router-bound saver ``accept_upload`` takes."""
    return filename, MagicMock()


class TestAcceptUpload:
    def test_publishes_a_durable_event_when_jobs_enabled(self):
        db = MagicMock()
        with (
            patch.object(ingestion_jobs.core_config.settings, "JOBS_ENABLED", True),
            patch.object(
                ingestion_jobs.activity_ingestion_upload_entry_service, "receive_upload", return_value=_received()
            ),
            patch.object(
                ingestion_jobs.activity_ingestion_upload_entry_service, "store_received_upload", return_value="abc.gpx"
            ),
            patch.object(ingestion_jobs.activity_ingestion_crud, "create_ingestion_job") as create,
            patch.object(ingestion_jobs.activity_ingestion_crud, "get_ingestion_job", return_value="job-view"),
            patch.object(
                ingestion_jobs.activity_ingestion_event_publishers.platform_publisher, "publish_committing"
            ) as publish,
            patch.object(
                ingestion_jobs.activity_ingestion_dispatch_service.activity_ingestion_background, "submit"
            ) as submit,
        ):
            result = ingestion_jobs.accept_upload(7, *_upload(), "storage", db)

        assert result == "job-view"
        # The row is staged, not committed, so it lands in the same transaction
        # as the outbox event.
        assert "commit" not in create.call_args.kwargs
        publish.assert_called_once()
        assert publish.call_args.kwargs["commit"] == db.commit
        # The payload carries only the job id: the key and owner are columns.
        assert publish.call_args.args[1] == {"job_id": create.call_args.args[0]}
        assert publish.call_args.kwargs["schema_version"] == ingestion_events.UploadedFilePayload.SCHEMA_VERSION
        submit.assert_not_called()

    def test_falls_back_to_the_background_pool_when_jobs_disabled(self):
        db = MagicMock()
        with (
            patch.object(ingestion_jobs.core_config.settings, "JOBS_ENABLED", False),
            patch.object(
                ingestion_jobs.activity_ingestion_upload_entry_service, "receive_upload", return_value=_received()
            ),
            patch.object(
                ingestion_jobs.activity_ingestion_upload_entry_service, "store_received_upload", return_value="abc.gpx"
            ),
            patch.object(ingestion_jobs.activity_ingestion_crud, "create_ingestion_job") as create,
            patch.object(ingestion_jobs.activity_ingestion_crud, "get_ingestion_job", return_value="job-view"),
            patch.object(
                ingestion_jobs.activity_ingestion_event_publishers.platform_publisher, "publish_committing"
            ) as publish,
            patch.object(
                ingestion_jobs.activity_ingestion_dispatch_service.activity_ingestion_background, "submit"
            ) as submit,
        ):
            ingestion_jobs.accept_upload(7, *_upload(), "storage", db)

        # Same client contract either way — only the executor differs.
        publish.assert_not_called()
        db.commit.assert_called_once()
        submit.assert_called_once_with(ingestion_jobs.run_upload_job, create.call_args.args[0], "storage")

    def test_a_rejected_file_never_leaves_a_job_behind(self):
        """Staging runs first, so a 4xx cannot create a row nobody will run."""
        db = MagicMock()
        with (
            patch.object(
                ingestion_jobs.activity_ingestion_upload_entry_service,
                "receive_upload",
                side_effect=core_exceptions.UnsupportedFormatError("nope"),
            ),
            patch.object(ingestion_jobs.activity_ingestion_crud, "create_ingestion_job") as create,
            pytest.raises(core_exceptions.UnsupportedFormatError),
        ):
            ingestion_jobs.accept_upload(7, *_upload("ride.txt"), "storage", db)

        create.assert_not_called()

    def test_the_staged_blob_is_discarded_when_queueing_fails(self):
        """Otherwise the blob would sit in storage forever with nothing to consume it."""
        db = MagicMock()
        with (
            patch.object(ingestion_jobs.core_config.settings, "JOBS_ENABLED", True),
            patch.object(
                ingestion_jobs.activity_ingestion_upload_entry_service, "receive_upload", return_value=_received()
            ),
            patch.object(
                ingestion_jobs.activity_ingestion_upload_entry_service, "store_received_upload", return_value="abc.gpx"
            ),
            patch.object(ingestion_jobs.activity_ingestion_crud, "create_ingestion_job"),
            patch.object(
                ingestion_jobs.activity_ingestion_event_publishers.platform_publisher,
                "publish_committing",
                side_effect=RuntimeError("outbox down"),
            ),
            patch.object(ingestion_jobs.activity_ingestion_upload_entry_service, "discard_staged_upload") as discard,
            pytest.raises(RuntimeError),
        ):
            ingestion_jobs.accept_upload(7, *_upload(), "storage", db)

        discard.assert_called_once_with("abc.gpx", ANY)


class TestRunUploadJob:
    def test_marks_completed_with_the_created_activity_ids(self):
        created = [MagicMock(id=11), MagicMock(id=12)]
        with (
            patch.object(ingestion_jobs.core_database, "SessionLocal") as session_local,
            patch.object(ingestion_jobs.activity_ingestion_crud, "get_job_work_item", return_value=(7, "abc.gpx")),
            patch.object(ingestion_jobs.activity_ingestion_crud, "mark_processing") as processing,
            patch.object(ingestion_jobs.activity_ingestion_crud, "mark_completed") as completed,
            patch.object(
                ingestion_jobs.activity_ingestion_upload_entry_service, "process_staged_upload", return_value=created
            ),
        ):
            session_local.return_value.__enter__.return_value = MagicMock()
            ingestion_jobs.run_upload_job("job-1", "storage")

        processing.assert_called_once()
        assert completed.call_args.args[0] == "job-1"
        assert completed.call_args.args[1] == [11, 12]

    @pytest.mark.parametrize("created", [[MagicMock(id=11)], []], ids=["imported", "nothing_parsed"])
    def test_the_blob_is_discarded_only_after_the_outcome_is_committed(self, created):
        """A crash before the commit must retry against the blob, not find it gone."""
        events: list[str] = []
        db = MagicMock()
        db.commit.side_effect = lambda: events.append("commit")
        with (
            patch.object(ingestion_jobs.core_database, "SessionLocal") as session_local,
            patch.object(ingestion_jobs.activity_ingestion_crud, "get_job_work_item", return_value=(7, "abc.gpx")),
            patch.object(ingestion_jobs.activity_ingestion_crud, "mark_processing"),
            patch.object(ingestion_jobs.activity_ingestion_crud, "mark_completed"),
            patch.object(ingestion_jobs.activity_ingestion_crud, "mark_failed"),
            patch.object(
                ingestion_jobs.activity_ingestion_upload_entry_service, "process_staged_upload", return_value=created
            ),
            patch.object(
                ingestion_jobs.activity_ingestion_upload_entry_service,
                "discard_staged_upload",
                side_effect=lambda *_a: events.append("discard"),
            ),
        ):
            session_local.return_value.__enter__.return_value = db
            ingestion_jobs.run_upload_job("job-1", "storage")

        # The first commit is ``processing``; the outcome's commit must precede the discard.
        assert events == ["commit", "commit", "discard"]

    def test_the_blob_survives_when_recording_the_outcome_fails(self):
        db = MagicMock()
        db.commit.side_effect = [None, RuntimeError("db down")]
        with (
            patch.object(ingestion_jobs.core_database, "SessionLocal") as session_local,
            patch.object(ingestion_jobs.activity_ingestion_crud, "get_job_work_item", return_value=(7, "abc.gpx")),
            patch.object(ingestion_jobs.activity_ingestion_crud, "mark_processing"),
            patch.object(ingestion_jobs.activity_ingestion_crud, "mark_completed"),
            patch.object(
                ingestion_jobs.activity_ingestion_upload_entry_service,
                "process_staged_upload",
                return_value=[MagicMock(id=11)],
            ),
            patch.object(ingestion_jobs.activity_ingestion_upload_entry_service, "discard_staged_upload") as discard,
            pytest.raises(RuntimeError),
        ):
            session_local.return_value.__enter__.return_value = db
            ingestion_jobs.run_upload_job("job-1", "storage")

        discard.assert_not_called()

    def test_a_consumed_job_is_a_no_op(self):
        """A retry after a successful import must not import the file twice."""
        with (
            patch.object(ingestion_jobs.core_database, "SessionLocal") as session_local,
            patch.object(ingestion_jobs.activity_ingestion_crud, "get_job_work_item", return_value=None),
            patch.object(ingestion_jobs.activity_ingestion_upload_entry_service, "process_staged_upload") as process,
        ):
            session_local.return_value.__enter__.return_value = MagicMock()
            ingestion_jobs.run_upload_job("job-1", "storage")

        process.assert_not_called()

    def test_an_unparseable_file_fails_with_a_specific_code(self):
        with (
            patch.object(ingestion_jobs.core_database, "SessionLocal") as session_local,
            patch.object(ingestion_jobs.activity_ingestion_crud, "get_job_work_item", return_value=(7, "abc.gpx")),
            patch.object(ingestion_jobs.activity_ingestion_crud, "mark_processing"),
            patch.object(ingestion_jobs.activity_ingestion_crud, "mark_failed") as failed,
            patch.object(
                ingestion_jobs.activity_ingestion_upload_entry_service, "process_staged_upload", return_value=None
            ),
        ):
            session_local.return_value.__enter__.return_value = MagicMock()
            ingestion_jobs.run_upload_job("job-1", "storage")

        assert failed.call_args.args[1] == activity_ingestion_constants.IngestionJobErrorCode.NO_ACTIVITIES_FOUND

    def test_a_rejected_file_is_terminal_immediately(self):
        """The same file fails identically on every retry, so don't burn attempts."""
        with (
            patch.object(ingestion_jobs.core_config.settings, "JOBS_ENABLED", True),
            patch.object(ingestion_jobs.core_database, "SessionLocal") as session_local,
            patch.object(ingestion_jobs.activity_ingestion_crud, "get_job_work_item", return_value=(7, "abc.gz")),
            patch.object(ingestion_jobs.activity_ingestion_crud, "mark_processing"),
            patch.object(ingestion_jobs, "fail_ingestion_job") as fail,
            patch.object(
                ingestion_jobs.activity_ingestion_upload_entry_service,
                "process_staged_upload",
                side_effect=core_exceptions.InvalidInputError("bad payload"),
            ),
        ):
            session_local.return_value.__enter__.return_value = MagicMock()
            # Recorded as terminal and returned, not raised: raising would hand the
            # runner a job it would retry and then find already finished.
            ingestion_jobs.run_upload_job("job-1", "storage")

        assert fail.call_args.args[1] == activity_ingestion_constants.IngestionJobErrorCode.INVALID_FILE
        assert fail.call_args.args[2] == "storage"
        assert fail.call_args.args[3] == "abc.gz"

    def test_a_transient_failure_is_left_for_the_retry(self):
        """Marking it failed here would tell the user a database blip rejected their file."""
        with (
            patch.object(ingestion_jobs.core_config.settings, "JOBS_ENABLED", True),
            patch.object(ingestion_jobs.core_database, "SessionLocal") as session_local,
            patch.object(ingestion_jobs.activity_ingestion_crud, "get_job_work_item", return_value=(7, "abc.gpx")),
            patch.object(ingestion_jobs.activity_ingestion_crud, "mark_processing"),
            patch.object(ingestion_jobs, "fail_ingestion_job") as fail,
            patch.object(
                ingestion_jobs.activity_ingestion_upload_entry_service,
                "process_staged_upload",
                side_effect=core_exceptions.ProcessingError(),
            ),
            pytest.raises(core_exceptions.ProcessingError),
        ):
            session_local.return_value.__enter__.return_value = MagicMock()
            ingestion_jobs.run_upload_job("job-1", "storage")

        fail.assert_not_called()

    def test_a_transient_failure_is_terminal_when_nothing_will_retry(self):
        """The fallback pool runs each job once, so waiting for a retry would hang the poller."""
        with (
            patch.object(ingestion_jobs.core_config.settings, "JOBS_ENABLED", False),
            patch.object(ingestion_jobs.core_database, "SessionLocal") as session_local,
            patch.object(ingestion_jobs.activity_ingestion_crud, "get_job_work_item", return_value=(7, "abc.gpx")),
            patch.object(ingestion_jobs.activity_ingestion_crud, "mark_processing"),
            patch.object(ingestion_jobs, "fail_ingestion_job") as fail,
            patch.object(
                ingestion_jobs.activity_ingestion_upload_entry_service,
                "process_staged_upload",
                side_effect=core_exceptions.ProcessingError(),
            ),
            pytest.raises(core_exceptions.ProcessingError),
        ):
            session_local.return_value.__enter__.return_value = MagicMock()
            ingestion_jobs.run_upload_job("job-1", "storage")

        assert fail.call_args.args[1] == activity_ingestion_constants.IngestionJobErrorCode.PROCESSING_FAILED


class TestFailUploadJob:
    def test_discards_the_blob_after_the_row_is_terminal(self):
        with (
            patch.object(ingestion_jobs.core_database, "SessionLocal") as session_local,
            patch.object(ingestion_jobs.activity_ingestion_crud, "mark_failed") as failed,
            patch.object(ingestion_jobs.activity_ingestion_upload_entry_service, "discard_staged_upload") as discard,
        ):
            session_local.return_value.__enter__.return_value = MagicMock()
            ingestion_jobs.fail_ingestion_job(
                "job-1",
                activity_ingestion_constants.IngestionJobErrorCode.PROCESSING_FAILED,
                "storage",
                "abc.gpx",
            )

        failed.assert_called_once()
        discard.assert_called_once_with("abc.gpx", "storage")

    def test_looks_the_key_up_when_the_caller_does_not_have_it(self):
        """The dead-letter path only knows the job id."""
        with (
            patch.object(ingestion_jobs.core_database, "SessionLocal") as session_local,
            patch.object(ingestion_jobs.activity_ingestion_crud, "get_job_work_item", return_value=(7, "abc.gpx")),
            patch.object(ingestion_jobs.activity_ingestion_crud, "mark_failed"),
            patch.object(ingestion_jobs.activity_ingestion_upload_entry_service, "discard_staged_upload") as discard,
        ):
            session_local.return_value.__enter__.return_value = MagicMock()
            ingestion_jobs.fail_ingestion_job(
                "job-1", activity_ingestion_constants.IngestionJobErrorCode.PROCESSING_FAILED, "storage"
            )

        discard.assert_called_once_with("abc.gpx", "storage")

    def test_a_bookkeeping_failure_never_propagates(self):
        """It must not mask the original import failure."""
        with (
            patch.object(ingestion_jobs.core_database, "SessionLocal", side_effect=RuntimeError("db down")),
            patch.object(ingestion_jobs.activity_ingestion_upload_entry_service, "discard_staged_upload"),
        ):
            ingestion_jobs.fail_ingestion_job(
                "job-1",
                activity_ingestion_constants.IngestionJobErrorCode.PROCESSING_FAILED,
                "storage",
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
            patch.object(ingestion_jobs.core_config.settings, "JOBS_RETENTION_DAYS", 90),
            patch.object(ingestion_jobs.core_database, "SessionLocal") as session_local,
            patch.object(ingestion_jobs.activity_ingestion_crud, "delete_jobs_before", return_value=3) as delete,
        ):
            platform = self._platform()
            session_local.return_value.__enter__.return_value = MagicMock()
            ingestion_jobs.prune_expired_ingestion_jobs(platform.lock, platform.clock)

        # The cutoff is the window applied to the platform clock, not wall time.
        assert delete.call_args.args[0] == datetime(2026, 4, 29, tzinfo=UTC)

    def test_is_inert_when_retention_is_disabled(self):
        platform = self._platform()
        with patch.object(ingestion_jobs.core_config.settings, "JOBS_RETENTION_DAYS", 0):
            ingestion_jobs.prune_expired_ingestion_jobs(platform.lock, platform.clock)

        platform.lock.try_acquire.assert_not_called()

    def test_skips_when_another_replica_holds_the_lock(self):
        platform = self._platform(acquired=False)
        with (
            patch.object(ingestion_jobs.core_config.settings, "JOBS_RETENTION_DAYS", 90),
            patch.object(ingestion_jobs.activity_ingestion_crud, "delete_jobs_before") as delete,
        ):
            ingestion_jobs.prune_expired_ingestion_jobs(platform.lock, platform.clock)

        delete.assert_not_called()


class TestFailStaleIngestionJobs:
    def test_skips_when_another_replica_holds_the_lock(self):
        platform = MagicMock()
        platform.lock.try_acquire.return_value.__enter__.return_value = False
        with patch.object(ingestion_jobs.activity_ingestion_crud, "fail_jobs_idle_since") as fail:
            ingestion_jobs.fail_stale_ingestion_jobs(platform.lock, platform.clock, platform.storage)

        fail.assert_not_called()

    def test_runs_on_the_schedule(self):
        import modules.activities.activity_ingestion.scheduled_jobs as scheduled_jobs

        runners = [job.func for job in scheduled_jobs.recurring_jobs()]

        assert scheduled_jobs.fail_stale_ingestion_jobs in runners


class TestErrorCodeFor:
    @pytest.mark.parametrize(
        ("error", "expected"),
        [
            (
                core_exceptions.UnsupportedFormatError("x"),
                activity_ingestion_constants.IngestionJobErrorCode.UNSUPPORTED_FORMAT,
            ),
            (core_exceptions.InvalidInputError("x"), activity_ingestion_constants.IngestionJobErrorCode.INVALID_FILE),
            (core_exceptions.ProcessingError(), activity_ingestion_constants.IngestionJobErrorCode.PROCESSING_FAILED),
        ],
    )
    def test_maps_known_failures(self, error, expected):
        assert ingestion_jobs.error_code_for(error) == expected

    def test_an_unexpected_failure_does_not_leak_its_message(self):
        """The exception text can carry paths and parser internals."""
        code = ingestion_jobs.error_code_for(RuntimeError("/srv/data/activity_files/secret.fit exploded"))
        assert code == activity_ingestion_constants.IngestionJobErrorCode.PROCESSING_FAILED


class TestGetJob:
    """The status read is scoped to the caller in the service, not the route."""

    @patch("modules.activities.activity_ingestion.service.activity_ingestion_crud")
    def test_returns_the_caller_s_job(self, mock_crud):
        import modules.activities.activity_ingestion.service as ingestion_jobs

        db = MagicMock()
        job = MagicMock()
        mock_crud.get_ingestion_job.return_value = job

        assert ingestion_jobs.get_job("job-1", 7, db) is job
        mock_crud.get_ingestion_job.assert_called_once_with("job-1", 7, db)

    @patch("modules.activities.activity_ingestion.service.activity_ingestion_crud")
    def test_another_user_s_job_is_absent_not_forbidden(self, mock_crud):
        """404 rather than 403, so the endpoint cannot confirm an id exists."""
        import core.exceptions as core_exceptions
        import modules.activities.activity_ingestion.service as ingestion_jobs

        mock_crud.get_ingestion_job.return_value = None

        with pytest.raises(core_exceptions.NotFoundError):
            ingestion_jobs.get_job("someone-elses-job", 7, MagicMock())
