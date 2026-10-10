"""Tests for the durable bulk-import-file subscriber."""

from unittest.mock import MagicMock, patch

import pytest
from jasil.events import Event
from jasil.jobs.registry import JobHandlerRegistry
from pydantic import ValidationError

import modules.activities.activity_ingestion.bulk_import_subscribers as bulk_import_subscribers
import modules.activities.activity_ingestion.events as ingestion_events


def _event(payload: dict, retry_count: int = 1, schema_version: int | None = None) -> Event:
    return Event(
        event_id="evt-1",
        event_type=ingestion_events.ACTIVITY_BULK_IMPORT_FILE,
        source="api:bulk_import",
        timestamp="2026-07-21T00:00:00+00:00",
        payload=payload,
        metadata={},
        retry_count=retry_count,
        schema_version=(
            ingestion_events.BulkImportFilePayload.SCHEMA_VERSION if schema_version is None else schema_version
        ),
    )


def _payload(**overrides) -> dict:
    base = {
        "job_id": "job-1",
        "storage_key": "3_abc.gpx",
        "filename": "x.gpx",
        "user_id": 3,
        "import_initiated_time": "2026-07-21",
    }
    base.update(overrides)
    return base


class TestPublishBulkImportFile:
    def test_declares_the_payload_version_it_writes(self):
        """The publisher defaults to version 1; without this every job would be
        rejected by its own version check."""
        db = MagicMock()
        with (
            patch.object(bulk_import_subscribers.platform_publisher, "publish_many_committing") as publish,
            patch.object(bulk_import_subscribers.staging, "stage_file", return_value="k1"),
        ):
            bulk_import_subscribers.publish_bulk_import_files([("job-1", "/tmp/x.gpx")], 3, "2026-07-21", db)

        assert publish.call_args.kwargs["schema_version"] == (ingestion_events.BulkImportFilePayload.SCHEMA_VERSION)

    def test_a_legacy_payload_is_refused_rather_than_guessed(self):
        """A v1 job names a local path this build cannot use from another node.

        Failing loudly dead-letters it (recoverable by re-dropping the file);
        defaulting the missing key would silently import nothing.
        """
        import jasil.event_versioning as platform_event_versioning

        legacy = _event({"file_path": "/tmp/x.gpx", "user_id": 3}, schema_version=1)
        with pytest.raises(platform_event_versioning.UnsupportedEventVersionError):
            bulk_import_subscribers.process_bulk_import_file_for_event(legacy)

    def test_stages_each_file_and_publishes_its_key(self):
        """The payload carries a key, not a path.

        A path only resolves on the node the file was dropped on, but any worker
        in the fleet may claim the job.
        """
        db = MagicMock()
        with (
            patch.object(bulk_import_subscribers.platform_publisher, "publish_many_committing") as publish,
            patch.object(bulk_import_subscribers.staging, "stage_file", side_effect=["k1", "k2"]) as stage,
        ):
            bulk_import_subscribers.publish_bulk_import_files(
                [("job-1", "/tmp/x.gpx"), ("job-2", "/tmp/y.fit")], 3, "2026-07-21", db
            )

        assert stage.call_count == 2
        args, kwargs = publish.call_args
        assert args[0] == ingestion_events.ACTIVITY_BULK_IMPORT_FILE
        assert args[1] == [
            {
                "job_id": "job-1",
                "storage_key": "k1",
                "filename": "x.gpx",
                "user_id": 3,
                "import_initiated_time": "2026-07-21",
            },
            {
                "job_id": "job-2",
                "storage_key": "k2",
                "filename": "y.fit",
                "user_id": 3,
                "import_initiated_time": "2026-07-21",
            },
        ]
        assert kwargs["source"] == "api:bulk_import"
        assert kwargs["db"] is db
        # One commit for the whole batch, not one per file.
        assert kwargs["commit"] == db.commit

    def test_originals_are_consumed_only_after_the_jobs_commit(self):
        db = MagicMock()
        with (
            patch.object(bulk_import_subscribers.platform_publisher, "publish_many_committing"),
            patch.object(bulk_import_subscribers.staging, "stage_file", return_value="k1"),
            patch.object(bulk_import_subscribers.staging, "settle") as settle,
            patch.object(bulk_import_subscribers.staging, "unstage") as unstage,
        ):
            bulk_import_subscribers.publish_bulk_import_files([("job-1", "/tmp/x.gpx")], 3, "2026-07-21", db)

        settle.assert_called_once_with([("k1", "/tmp/x.gpx")], 3)
        unstage.assert_not_called()

    def test_a_publish_failure_leaves_the_dropped_files_alone(self):
        """Consuming them before the jobs are durable would eat the import."""
        db = MagicMock()
        with (
            patch.object(
                bulk_import_subscribers.platform_publisher,
                "publish_many_committing",
                side_effect=RuntimeError("outbox down"),
            ),
            patch.object(bulk_import_subscribers.staging, "stage_file", return_value="k1"),
            patch.object(bulk_import_subscribers.staging, "settle") as settle,
            patch.object(bulk_import_subscribers.staging, "unstage") as unstage,
            pytest.raises(RuntimeError),
        ):
            bulk_import_subscribers.publish_bulk_import_files([("job-1", "/tmp/x.gpx")], 3, "2026-07-21", db)

        settle.assert_not_called()
        unstage.assert_called_once_with(["k1"])

    def test_staging_failure_propagates(self):
        """This event *is* the work: a swallowed failure would silently drop the import."""
        db = MagicMock()
        with (
            patch.object(bulk_import_subscribers.staging, "stage_file", return_value="k1"),
            patch.object(
                bulk_import_subscribers.platform_publisher,
                "publish_many_committing",
                side_effect=RuntimeError("outbox down"),
            ),
            pytest.raises(RuntimeError),
        ):
            bulk_import_subscribers.publish_bulk_import_files([("job-1", "/tmp/x.gpx")], 3, "2026-07-21", db)


class TestProcessBulkImportFileForEvent:
    @staticmethod
    def _run(event, *, materialized="/tmp/work/x.gpx", store=None):
        ctx = MagicMock()
        ctx.__enter__ = MagicMock(return_value=materialized)
        ctx.__exit__ = MagicMock(return_value=False)
        with (
            patch.object(bulk_import_subscribers.staging, "materialized", return_value=ctx),
            patch.object(bulk_import_subscribers.staging, "discard") as discard,
            patch.object(bulk_import_subscribers.staging, "move_to_errors") as move,
            patch.object(bulk_import_subscribers.core_database, "SessionLocal"),
            patch.object(bulk_import_subscribers, "ingestion_jobs_crud") as jobs,
            patch.object(bulk_import_subscribers.bulk_entry, "store_bulk_import_file", side_effect=store) as run,
        ):
            error = None
            try:
                bulk_import_subscribers.process_bulk_import_file_for_event(event)
            except Exception as err:
                error = err
        return run, discard, move, error, jobs

    def test_imports_the_materialized_file_then_discards_the_blob(self):
        run, discard, move, error, _jobs = self._run(_event(_payload()))

        assert error is None
        assert run.call_args.args[1] == "/tmp/work/x.gpx"
        discard.assert_called_once_with("3_abc.gpx")
        move.assert_not_called()

    def test_the_caller_handle_follows_the_import(self):
        """The 202 hands back a job id; it has to report the outcome."""
        activity = MagicMock(id=42)
        _run, _discard, _move, error, jobs = self._run(_event(_payload()), store=[[activity]])

        assert error is None
        assert jobs.mark_processing.call_args.args[0] == "job-1"
        assert jobs.mark_completed.call_args.args[:2] == ("job-1", [42])
        jobs.mark_failed.assert_not_called()

    def test_a_v2_event_without_a_handle_still_imports(self):
        """A backlog event staged before handles existed has no row to move."""
        _run, discard, _move, error, jobs = self._run(_event(_payload(), schema_version=2))

        assert error is None
        discard.assert_called_once_with("3_abc.gpx")
        jobs.mark_processing.assert_not_called()
        jobs.mark_completed.assert_not_called()

    def test_a_missing_blob_is_a_no_op_not_a_failure(self):
        """A duplicate delivery after a successful import must not retry forever."""
        run, discard, move, error, _jobs = self._run(_event(_payload()), materialized=None)

        assert error is None
        run.assert_not_called()
        discard.assert_not_called()
        move.assert_not_called()

    def test_reraises_without_moving_before_the_last_attempt(self):
        _run, discard, move, error, jobs = self._run(_event(_payload(), retry_count=1), store=RuntimeError("bad file"))

        assert isinstance(error, RuntimeError)
        move.assert_not_called()
        discard.assert_not_called()
        # Still retryable, so the owner is not told it failed.
        jobs.mark_failed.assert_not_called()

    def test_moves_the_blob_to_the_error_area_on_the_last_attempt(self):
        with patch.object(bulk_import_subscribers.core_config.settings, "JOBS_MAX_ATTEMPTS", 3):
            _run, _discard, move, error, jobs = self._run(
                _event(_payload(), retry_count=3), store=RuntimeError("bad file")
            )

        assert isinstance(error, RuntimeError)
        move.assert_called_once_with("3_abc.gpx", 3, "x.gpx")
        assert jobs.mark_failed.call_args.args[0] == "job-1"

    @pytest.mark.parametrize(
        "payload",
        [
            {"job_id": "job-1", "filename": "x.gpx", "user_id": 3},
            {"job_id": "job-1", "storage_key": "3_abc.gpx", "user_id": 3},
            {"job_id": "job-1", "storage_key": "3_abc.gpx", "filename": "x.gpx", "user_id": "three"},
            {"storage_key": "3_abc.gpx", "filename": "x.gpx", "user_id": 3},
        ],
        ids=["no-key", "no-filename", "non-int-user", "no-job-id"],
    )
    def test_a_malformed_payload_raises(self, payload):
        """Raising surfaces via retry/dead-letter instead of silently completing."""
        with pytest.raises(ValidationError):
            bulk_import_subscribers.process_bulk_import_file_for_event(_event(payload))


class TestRegistration:
    def test_registers_the_durable_handler(self):
        registry = JobHandlerRegistry()
        bulk_import_subscribers.register_bulk_import_durable_handlers(registry)

        assert registry.get(bulk_import_subscribers.BULK_IMPORT_FILE_SUBSCRIBER_ID) is not None
