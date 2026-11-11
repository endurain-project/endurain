"""Tests for accepting, running and pruning activity upload jobs."""

from datetime import UTC, datetime
from unittest.mock import ANY, MagicMock, patch

import pytest
from sqlalchemy.exc import OperationalError

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
            ingestion_jobs.run_upload_job("job-1", MagicMock())

        processing.assert_called_once()
        assert completed.call_args.args[0] == "job-1"
        assert completed.call_args.args[1] == [11, 12]

    def test_the_owner_is_told_when_the_import_completes(self):
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
            patch.object(ingestion_jobs.websocket_integration, "push_job_changed") as push,
        ):
            session_local.return_value.__enter__.return_value = MagicMock()
            ingestion_jobs.run_upload_job("job-1", MagicMock())

        push.assert_called_once_with(7, "job-1", "activity_upload")

    def test_the_owner_is_told_when_nothing_could_be_parsed(self):
        with (
            patch.object(ingestion_jobs.core_database, "SessionLocal") as session_local,
            patch.object(ingestion_jobs.activity_ingestion_crud, "get_job_work_item", return_value=(7, "abc.gpx")),
            patch.object(ingestion_jobs.activity_ingestion_crud, "mark_processing"),
            patch.object(ingestion_jobs.activity_ingestion_crud, "mark_failed"),
            patch.object(
                ingestion_jobs.activity_ingestion_upload_entry_service, "process_staged_upload", return_value=None
            ),
            patch.object(ingestion_jobs.websocket_integration, "push_job_changed") as push,
        ):
            session_local.return_value.__enter__.return_value = MagicMock()
            ingestion_jobs.run_upload_job("job-1", MagicMock())

        push.assert_called_once_with(7, "job-1", "activity_upload")

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
            ingestion_jobs.run_upload_job("job-1", MagicMock())

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
            ingestion_jobs.run_upload_job("job-1", MagicMock())

        discard.assert_not_called()

    def test_a_consumed_job_is_a_no_op(self):
        """A retry after a successful import must not import the file twice."""
        with (
            patch.object(ingestion_jobs.core_database, "SessionLocal") as session_local,
            patch.object(ingestion_jobs.activity_ingestion_crud, "get_job_work_item", return_value=None),
            patch.object(ingestion_jobs.activity_ingestion_upload_entry_service, "process_staged_upload") as process,
        ):
            session_local.return_value.__enter__.return_value = MagicMock()
            ingestion_jobs.run_upload_job("job-1", MagicMock())

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
            ingestion_jobs.run_upload_job("job-1", MagicMock())

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
            ingestion_jobs.run_upload_job("job-1", MagicMock())

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
            ingestion_jobs.run_upload_job("job-1", MagicMock())

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

    def test_a_database_failure_never_propagates_and_keeps_the_blob(self):
        """It must not mask the original import failure, and the row still names the blob."""
        with (
            patch.object(
                ingestion_jobs.core_database,
                "SessionLocal",
                side_effect=OperationalError("stmt", {}, Exception("down")),
            ),
            patch.object(ingestion_jobs.activity_ingestion_upload_entry_service, "discard_staged_upload") as discard,
        ):
            ingestion_jobs.fail_ingestion_job(
                "job-1",
                activity_ingestion_constants.IngestionJobErrorCode.PROCESSING_FAILED,
                "storage",
                "abc.gpx",
            )

        discard.assert_not_called()

    def test_a_failed_commit_keeps_the_blob(self):
        with (
            patch.object(ingestion_jobs.core_database, "SessionLocal") as session_local,
            patch.object(ingestion_jobs.activity_ingestion_crud, "mark_failed"),
            patch.object(ingestion_jobs.activity_ingestion_upload_entry_service, "discard_staged_upload") as discard,
        ):
            session_local.return_value.__enter__.return_value.commit.side_effect = OperationalError(
                "stmt", {}, Exception("down")
            )
            ingestion_jobs.fail_ingestion_job(
                "job-1",
                activity_ingestion_constants.IngestionJobErrorCode.PROCESSING_FAILED,
                "storage",
                "abc.gpx",
            )

        discard.assert_not_called()


class TestReleaseIngestionJob:
    def test_a_database_failure_is_logged_not_raised(self):
        with patch.object(
            ingestion_jobs.core_database, "SessionLocal", side_effect=OperationalError("stmt", {}, Exception("down"))
        ):
            ingestion_jobs.release_ingestion_job("job-1")

    def test_an_unexpected_error_propagates(self):
        with (
            patch.object(ingestion_jobs.core_database, "SessionLocal", side_effect=RuntimeError("bug")),
            pytest.raises(RuntimeError),
        ):
            ingestion_jobs.release_ingestion_job("job-1")


class TestPruneExpiredUploadJobs:
    def _platform(self) -> MagicMock:
        platform = MagicMock()
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
            ingestion_jobs.prune_expired_ingestion_jobs(platform.clock)

        # The cutoff is the window applied to the platform clock, not wall time.
        assert delete.call_args.args[0] == datetime(2026, 4, 29, tzinfo=UTC)

    def test_is_inert_when_retention_is_disabled(self):
        platform = self._platform()
        with (
            patch.object(ingestion_jobs.core_config.settings, "JOBS_RETENTION_DAYS", 0),
            patch.object(ingestion_jobs.core_database, "SessionLocal") as session_local,
        ):
            ingestion_jobs.prune_expired_ingestion_jobs(platform.clock)

        session_local.assert_not_called()


class TestFailStaleIngestionJobs:
    def test_a_backlog_larger_than_one_batch_is_failed_a_batch_per_transaction(self):
        batch = ingestion_jobs._STALE_JOB_BATCH_SIZE
        full = [(f"job-{i}", None) for i in range(batch)]
        last = [("job-last", "staged.gpx")]
        platform = MagicMock()
        sessions = MagicMock()
        with (
            patch.object(ingestion_jobs.core_database, "SessionLocal", sessions),
            patch.object(
                ingestion_jobs.activity_ingestion_crud, "fail_jobs_idle_since", side_effect=[full, last]
            ) as fail,
            patch.object(ingestion_jobs.activity_ingestion_upload_entry_service, "discard_staged_upload") as discard,
        ):
            ingestion_jobs.fail_stale_ingestion_jobs(platform.clock, platform.storage)

        assert fail.call_count == 2
        assert all(call.args[2] == batch for call in fail.call_args_list)
        assert sessions.return_value.__enter__.return_value.commit.call_count == 2
        discard.assert_called_once_with("staged.gpx", platform.storage)

    def test_a_single_short_batch_ends_the_pass(self):
        platform = MagicMock()
        with (
            patch.object(ingestion_jobs.core_database, "SessionLocal"),
            patch.object(ingestion_jobs.activity_ingestion_crud, "fail_jobs_idle_since", return_value=[]) as fail,
        ):
            ingestion_jobs.fail_stale_ingestion_jobs(platform.clock, platform.storage)

        fail.assert_called_once()

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


class TestFailIngestionJobTellsTheOwner:
    def _fail(self, failed):
        with (
            patch.object(ingestion_jobs.core_database, "SessionLocal"),
            patch.object(ingestion_jobs.activity_ingestion_crud, "mark_failed", return_value=failed),
            patch.object(ingestion_jobs.activity_ingestion_upload_entry_service, "discard_staged_upload"),
            patch.object(ingestion_jobs.websocket_integration, "push_job_changed") as push,
        ):
            ingestion_jobs.fail_ingestion_job(
                "job-1", activity_ingestion_constants.IngestionJobErrorCode.INVALID_FILE, "storage", "abc.gpx"
            )
        return push

    def test_the_owner_of_the_failed_job_is_told(self):
        self._fail((7, activity_ingestion_constants.IngestionJobKind.BULK_IMPORT)).assert_called_once_with(
            7, "job-1", "activity_bulk_import"
        )

    def test_nobody_is_told_when_the_job_was_already_terminal(self):
        self._fail(None).assert_not_called()
