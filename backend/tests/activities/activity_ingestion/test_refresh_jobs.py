"""Tests for accepting and running provider refresh jobs."""

from datetime import UTC, datetime
from unittest.mock import MagicMock, patch

import pytest

import modules.activities.activity_ingestion.constants as activity_ingestion_constants
import modules.activities.activity_ingestion.events as ingestion_events
import modules.activities.activity_ingestion.provider_registry as provider_registry
import modules.activities.activity_ingestion.service as ingestion_jobs


class TestAcceptRefresh:
    def test_publishes_a_durable_event_when_jobs_enabled(self):
        db = MagicMock()
        with (
            patch.object(ingestion_jobs.core_config.settings, "JOBS_ENABLED", True),
            patch.object(ingestion_jobs.activity_ingestion_crud, "create_ingestion_job") as create,
            patch.object(ingestion_jobs.activity_ingestion_crud, "get_ingestion_job", return_value="job-view"),
            patch.object(
                ingestion_jobs.activity_ingestion_event_publishers.platform_publisher, "publish_committing"
            ) as publish,
            patch.object(
                ingestion_jobs.activity_ingestion_dispatch_service.activity_ingestion_background, "submit"
            ) as submit,
        ):
            result = ingestion_jobs.accept_refresh(7, "storage", db)

        assert result == "job-view"
        assert create.call_args.args[2] == activity_ingestion_constants.IngestionJobKind.REFRESH
        # Row and event land in one transaction, so a crash between them cannot
        # leave a job nobody will run.
        assert "commit" not in create.call_args.kwargs
        assert publish.call_args.kwargs["commit"] == db.commit
        assert publish.call_args.args[1] == {"job_id": create.call_args.args[0]}
        assert publish.call_args.kwargs["schema_version"] == ingestion_events.RefreshRequestedPayload.SCHEMA_VERSION
        submit.assert_not_called()

    def test_falls_back_to_the_background_pool_when_jobs_disabled(self):
        db = MagicMock()
        with (
            patch.object(ingestion_jobs.core_config.settings, "JOBS_ENABLED", False),
            patch.object(ingestion_jobs.activity_ingestion_crud, "create_ingestion_job") as create,
            patch.object(ingestion_jobs.activity_ingestion_crud, "get_ingestion_job", return_value="job-view"),
            patch.object(
                ingestion_jobs.activity_ingestion_event_publishers.platform_publisher, "publish_committing"
            ) as publish,
            patch.object(
                ingestion_jobs.activity_ingestion_dispatch_service.activity_ingestion_background, "submit"
            ) as submit,
        ):
            ingestion_jobs.accept_refresh(7, "storage", db)

        # Same client contract either way — only the executor differs.
        publish.assert_not_called()
        db.commit.assert_called_once()
        submit.assert_called_once_with(ingestion_jobs.run_refresh_job, create.call_args.args[0], "storage")

    def test_a_refresh_job_carries_no_file_fields(self):
        db = MagicMock()
        with (
            patch.object(ingestion_jobs.core_config.settings, "JOBS_ENABLED", True),
            patch.object(ingestion_jobs.activity_ingestion_crud, "create_ingestion_job") as create,
            patch.object(ingestion_jobs.activity_ingestion_crud, "get_ingestion_job", return_value="job-view"),
            patch.object(ingestion_jobs.activity_ingestion_event_publishers.platform_publisher, "publish_committing"),
        ):
            ingestion_jobs.accept_refresh(7, "storage", db)

        assert "filename" not in create.call_args.kwargs
        assert "staged_key" not in create.call_args.kwargs


_SCOPE = (7, None, None, None)


class TestRunRefreshJob:
    def _patches(self, scope=_SCOPE):
        return (
            patch.object(ingestion_jobs.core_database, "SessionLocal"),
            patch.object(ingestion_jobs.activity_ingestion_crud, "get_refresh_scope", return_value=scope),
            patch.object(ingestion_jobs.activity_ingestion_crud, "mark_processing"),
            patch.object(ingestion_jobs.activity_ingestion_crud, "mark_completed"),
        )

    def test_marks_completed_with_the_synced_activity_ids(self):
        synced = [MagicMock(id=11), MagicMock(id=12)]
        with (
            patch.object(ingestion_jobs.core_database, "SessionLocal"),
            patch.object(ingestion_jobs.activity_ingestion_crud, "get_refresh_scope", return_value=_SCOPE),
            patch.object(ingestion_jobs.activity_ingestion_crud, "mark_processing") as processing,
            patch.object(ingestion_jobs.activity_ingestion_crud, "mark_completed") as completed,
            patch.object(
                ingestion_jobs.activity_ingestion_refresh_entry_service, "sync_linked_providers", return_value=synced
            ),
        ):
            ingestion_jobs.run_refresh_job("job-1", "storage")

        processing.assert_called_once()
        assert completed.call_args.args[1] == [11, 12]

    def test_the_scope_comes_from_the_row_not_the_event(self):
        """A tampered payload must not make the worker sync somebody else's providers."""
        start = datetime(2026, 1, 1, tzinfo=UTC)
        end = datetime(2026, 1, 8, tzinfo=UTC)
        with (
            patch.object(ingestion_jobs.core_database, "SessionLocal"),
            patch.object(
                ingestion_jobs.activity_ingestion_crud,
                "get_refresh_scope",
                return_value=(42, "strava", start, end),
            ),
            patch.object(ingestion_jobs.activity_ingestion_crud, "mark_processing"),
            patch.object(ingestion_jobs.activity_ingestion_crud, "mark_completed"),
            patch.object(
                ingestion_jobs.activity_ingestion_refresh_entry_service, "sync_linked_providers", return_value=[]
            ) as sync,
        ):
            ingestion_jobs.run_refresh_job("job-1", "storage")

        sync.assert_called_once_with(42, start, end, provider="strava")

    def test_no_session_is_open_while_the_providers_run(self):
        """A transaction held across a provider round trip is what this job must not do."""
        open_sessions = 0
        seen_during_sync: list[int] = []

        class _Session:
            def __enter__(self):
                nonlocal open_sessions
                open_sessions += 1
                return MagicMock()

            def __exit__(self, *_exc):
                nonlocal open_sessions
                open_sessions -= 1
                return False

        def _sync(*_args, **_kwargs):
            seen_during_sync.append(open_sessions)
            return []

        with (
            patch.object(ingestion_jobs.core_database, "SessionLocal", _Session),
            patch.object(ingestion_jobs.activity_ingestion_crud, "get_refresh_scope", return_value=_SCOPE),
            patch.object(ingestion_jobs.activity_ingestion_crud, "mark_processing"),
            patch.object(ingestion_jobs.activity_ingestion_crud, "mark_completed"),
            patch.object(
                ingestion_jobs.activity_ingestion_refresh_entry_service, "sync_linked_providers", side_effect=_sync
            ),
        ):
            ingestion_jobs.run_refresh_job("job-1", "storage")

        assert seen_during_sync == [0]

    def test_an_unknown_job_is_a_no_op(self):
        with (
            patch.object(ingestion_jobs.core_database, "SessionLocal"),
            patch.object(ingestion_jobs.activity_ingestion_crud, "get_refresh_scope", return_value=None),
            patch.object(ingestion_jobs.activity_ingestion_refresh_entry_service, "sync_linked_providers") as sync,
        ):
            ingestion_jobs.run_refresh_job("job-1", "storage")

        sync.assert_not_called()

    def test_a_provider_failure_is_left_for_the_retry(self):
        """Provider outages and rate limits are exactly what backoff is for."""
        with (
            patch.object(ingestion_jobs.core_config.settings, "JOBS_ENABLED", True),
            patch.object(ingestion_jobs.core_database, "SessionLocal"),
            patch.object(ingestion_jobs.activity_ingestion_crud, "get_refresh_scope", return_value=_SCOPE),
            patch.object(ingestion_jobs.activity_ingestion_crud, "mark_processing"),
            patch.object(ingestion_jobs, "fail_ingestion_job") as fail,
            patch.object(
                ingestion_jobs.activity_ingestion_refresh_entry_service,
                "sync_linked_providers",
                side_effect=RuntimeError("strava is down"),
            ),
            pytest.raises(RuntimeError),
        ):
            ingestion_jobs.run_refresh_job("job-1", "storage")

        fail.assert_not_called()

    def test_a_provider_failure_is_terminal_when_nothing_will_retry(self):
        with (
            patch.object(ingestion_jobs.core_config.settings, "JOBS_ENABLED", False),
            patch.object(ingestion_jobs.core_database, "SessionLocal"),
            patch.object(ingestion_jobs.activity_ingestion_crud, "get_refresh_scope", return_value=_SCOPE),
            patch.object(ingestion_jobs.activity_ingestion_crud, "mark_processing"),
            patch.object(ingestion_jobs, "fail_ingestion_job") as fail,
            patch.object(
                ingestion_jobs.activity_ingestion_refresh_entry_service,
                "sync_linked_providers",
                side_effect=RuntimeError("strava is down"),
            ),
            pytest.raises(RuntimeError),
        ):
            ingestion_jobs.run_refresh_job("job-1", "storage")

        assert fail.call_args.args[1] == activity_ingestion_constants.IngestionJobErrorCode.PROVIDER_UNAVAILABLE

    def test_a_refresh_that_found_nothing_still_completes(self):
        """Nothing new is a normal outcome, not a failure."""
        with (
            patch.object(ingestion_jobs.core_database, "SessionLocal"),
            patch.object(ingestion_jobs.activity_ingestion_crud, "get_refresh_scope", return_value=_SCOPE),
            patch.object(ingestion_jobs.activity_ingestion_crud, "mark_processing"),
            patch.object(ingestion_jobs.activity_ingestion_crud, "mark_completed") as completed,
            patch.object(ingestion_jobs.activity_ingestion_crud, "mark_failed") as failed,
            patch.object(
                ingestion_jobs.activity_ingestion_refresh_entry_service, "sync_linked_providers", return_value=[]
            ),
        ):
            ingestion_jobs.run_refresh_job("job-1", "storage")

        assert completed.call_args.args[1] == []
        failed.assert_not_called()


class TestScheduledRefreshFanOut:
    def _provider(self, name: str, pages: list[list[int]]):
        calls: list[tuple[int, int]] = []
        remaining = list(pages)

        def _linked(after_id: int, limit: int) -> list[int]:
            calls.append((after_id, limit))
            return remaining.pop(0) if remaining else []

        provider_registry.register(provider_registry.ActivityProvider(name, lambda *_a: None, _linked))
        return calls

    @pytest.fixture(autouse=True)
    def _registry(self):
        provider_registry.clear()
        yield
        provider_registry.clear()

    @staticmethod
    def _lock(acquired: bool = True) -> MagicMock:
        lock = MagicMock()
        lock.try_acquire.return_value.__enter__.return_value = acquired
        return lock

    def test_queues_one_job_per_linked_user_and_runs_each_locally(self):
        self._provider("strava", [[1, 2], [3]])
        db = MagicMock()
        with (
            patch.object(ingestion_jobs.core_config.settings, "JOBS_ENABLED", False),
            patch.object(ingestion_jobs.core_database, "SessionLocal") as session_local,
            patch.object(
                ingestion_jobs.activity_ingestion_crud, "get_user_ids_with_active_refresh", return_value=set()
            ),
            patch.object(ingestion_jobs.activity_ingestion_crud, "create_ingestion_job") as create,
            patch.object(
                ingestion_jobs.activity_ingestion_dispatch_service.activity_ingestion_background, "submit"
            ) as submit,
        ):
            session_local.return_value.__enter__.return_value = db
            queued = ingestion_jobs.enqueue_scheduled_refreshes(self._lock(), "storage")

        assert queued == 3
        assert [call.args[1] for call in create.call_args_list] == [1, 2, 3]
        assert submit.call_count == 3
        # One commit per page, not per user.
        assert db.commit.call_count == 2

    def test_a_user_linked_to_two_providers_gets_one_job(self):
        self._provider("strava", [[1, 2]])
        self._provider("garminconnect", [[2, 3]])
        with (
            patch.object(ingestion_jobs.core_config.settings, "JOBS_ENABLED", False),
            patch.object(ingestion_jobs.core_database, "SessionLocal"),
            patch.object(
                ingestion_jobs.activity_ingestion_crud, "get_user_ids_with_active_refresh", return_value=set()
            ),
            patch.object(ingestion_jobs.activity_ingestion_crud, "create_ingestion_job") as create,
            patch.object(ingestion_jobs.activity_ingestion_dispatch_service.activity_ingestion_background, "submit"),
        ):
            ingestion_jobs.enqueue_scheduled_refreshes(self._lock(), "storage")

        assert sorted(call.args[1] for call in create.call_args_list) == [1, 2, 3]

    def test_a_user_whose_previous_refresh_has_not_finished_is_skipped(self):
        """A backed-up queue must not grow by a job per user per run."""
        self._provider("strava", [[1, 2]])
        with (
            patch.object(ingestion_jobs.core_config.settings, "JOBS_ENABLED", False),
            patch.object(ingestion_jobs.core_database, "SessionLocal"),
            patch.object(ingestion_jobs.activity_ingestion_crud, "get_user_ids_with_active_refresh", return_value={1}),
            patch.object(ingestion_jobs.activity_ingestion_crud, "create_ingestion_job") as create,
            patch.object(ingestion_jobs.activity_ingestion_dispatch_service.activity_ingestion_background, "submit"),
        ):
            queued = ingestion_jobs.enqueue_scheduled_refreshes(self._lock(), "storage")

        assert queued == 1
        assert [call.args[1] for call in create.call_args_list] == [2]

    def test_the_durable_profile_publishes_one_batch_and_runs_nothing_inline(self):
        self._provider("strava", [[1, 2]])
        with (
            patch.object(ingestion_jobs.core_config.settings, "JOBS_ENABLED", True),
            patch.object(ingestion_jobs.core_database, "SessionLocal") as session_local,
            patch.object(
                ingestion_jobs.activity_ingestion_crud, "get_user_ids_with_active_refresh", return_value=set()
            ),
            patch.object(ingestion_jobs.activity_ingestion_crud, "create_ingestion_job"),
            patch.object(
                ingestion_jobs.activity_ingestion_event_publishers.platform_publisher, "publish_many_committing"
            ) as publish_many,
            patch.object(
                ingestion_jobs.activity_ingestion_dispatch_service.activity_ingestion_background, "submit"
            ) as submit,
        ):
            session_local.return_value.__enter__.return_value = MagicMock()
            ingestion_jobs.enqueue_scheduled_refreshes(self._lock(), "storage")

        publish_many.assert_called_once()
        assert len(publish_many.call_args.args[1]) == 2
        submit.assert_not_called()

    def test_another_replica_holding_the_lock_means_nothing_is_queued(self):
        calls = self._provider("strava", [[1]])
        with patch.object(ingestion_jobs.activity_ingestion_crud, "create_ingestion_job") as create:
            queued = ingestion_jobs.enqueue_scheduled_refreshes(self._lock(acquired=False), "storage")

        assert queued == 0
        assert calls == []
        create.assert_not_called()

    def test_pages_each_provider_by_cursor(self):
        calls = self._provider("strava", [[1, 2], [3]])
        with (
            patch.object(ingestion_jobs.core_config.settings, "JOBS_ENABLED", False),
            patch.object(ingestion_jobs.core_database, "SessionLocal"),
            patch.object(
                ingestion_jobs.activity_ingestion_crud, "get_user_ids_with_active_refresh", return_value=set()
            ),
            patch.object(ingestion_jobs.activity_ingestion_crud, "create_ingestion_job"),
            patch.object(ingestion_jobs.activity_ingestion_dispatch_service.activity_ingestion_background, "submit"),
        ):
            ingestion_jobs.enqueue_scheduled_refreshes(self._lock(), "storage")

        assert [after_id for after_id, _limit in calls] == [0, 2, 3]
