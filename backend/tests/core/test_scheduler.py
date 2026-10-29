"""Tests for core.scheduler — APScheduler setup and lifecycle."""

from unittest.mock import AsyncMock, MagicMock, patch

from jasil.backends.state_memory import MemoryState
from jasil.providers import StateBackendUnavailableError


class TestSchedulerJobId:
    """Tests for _scheduler_job_id helper."""

    def test_generates_stable_id_from_description(self):
        from core.scheduler import _scheduler_job_id

        result = _scheduler_job_id("refresh Strava user tokens every 60 minutes")
        assert result == "endurain_refresh_strava_user_tokens_every_60_minutes"

    def test_handles_single_word_description(self):
        from core.scheduler import _scheduler_job_id

        result = _scheduler_job_id("test")
        assert result == "endurain_test"


class TestStartScheduler:
    """Tests for start_scheduler."""

    def test_starts_scheduler_when_not_running(self):
        with patch("core.scheduler.scheduler") as mock_scheduler:
            mock_scheduler.running = False
            from core.scheduler import start_scheduler

            start_scheduler()
            mock_scheduler.start.assert_called_once_with()

    def test_skips_start_when_already_running(self):
        with patch("core.scheduler.scheduler") as mock_scheduler:
            mock_scheduler.running = True
            from core.scheduler import start_scheduler

            start_scheduler()
            mock_scheduler.start.assert_not_called()

    def test_registers_every_job_it_is_handed(self):
        with (
            patch("core.scheduler.scheduler") as mock_scheduler,
            patch("core.scheduler.add_scheduler_job") as mock_add_job,
        ):
            mock_scheduler.running = False
            from core.scheduler import ScheduledJob, start_scheduler

            def dummy():
                pass

            start_scheduler([ScheduledJob(dummy, 5, "a"), ScheduledJob(dummy, 10, "b")])
            assert mock_add_job.call_count == 2

    def test_registers_locked_sync_job_through_sync_adapter(self):
        with (
            patch("core.scheduler.scheduler") as mock_scheduler,
            patch("core.scheduler.add_scheduler_job") as mock_add_job,
        ):
            mock_scheduler.running = True
            from core.scheduler import ScheduledJob, run_due_job, start_scheduler

            operation = MagicMock()
            start_scheduler([ScheduledJob(operation, 5, "locked", [1], "provider_sync")])

            mock_add_job.assert_called_once_with(
                run_due_job,
                "interval",
                5,
                ("provider_sync", 5, operation, 1),
                "locked",
            )

    def test_registers_locked_async_job_through_async_adapter(self):
        with (
            patch("core.scheduler.scheduler") as mock_scheduler,
            patch("core.scheduler.add_scheduler_job") as mock_add_job,
        ):
            mock_scheduler.running = True
            from core.scheduler import ScheduledJob, _run_due_async_job, start_scheduler

            async def operation(value):
                return value

            start_scheduler([ScheduledJob(operation, 5, "locked", [1], "provider_async")])

            mock_add_job.assert_called_once_with(
                _run_due_async_job,
                "interval",
                5,
                ("provider_async", 5, operation, 1),
                "locked",
            )

    def test_registers_nothing_when_handed_nothing(self):
        """The scheduler owns no domain job list of its own."""
        with (
            patch("core.scheduler.scheduler") as mock_scheduler,
            patch("core.scheduler.add_scheduler_job") as mock_add_job,
        ):
            mock_scheduler.running = False
            from core.scheduler import start_scheduler

            start_scheduler()
            mock_add_job.assert_not_called()

    def test_queues_the_one_shot_retention_prune(self):
        with patch("core.scheduler.scheduler") as mock_scheduler:
            mock_scheduler.running = True
            import jasil.retention as platform_retention

            from core.scheduler import start_scheduler

            start_scheduler()
            assert mock_scheduler.add_job.call_args.args[0] is platform_retention.prune_expired_records


class TestAddSchedulerJob:
    """Tests for add_scheduler_job."""

    def test_adds_job_successfully(self):
        with (
            patch("core.scheduler.scheduler") as mock_scheduler,
            patch("core.scheduler.logger") as mock_log,
        ):
            from core.scheduler import add_scheduler_job

            def dummy():
                pass

            add_scheduler_job(dummy, "interval", 60, [True], "test job every 60 minutes")
            mock_scheduler.add_job.assert_called_once_with(
                dummy,
                "interval",
                minutes=60,
                args=[True],
                id="endurain_test_job_every_60_minutes",
                replace_existing=True,
            )
            assert len(mock_log.method_calls) == 1

    def test_logs_error_when_add_job_fails(self):
        with (
            patch("core.scheduler.scheduler") as mock_scheduler,
            patch("core.scheduler.logger") as mock_log,
        ):
            mock_scheduler.add_job.side_effect = ValueError("something went wrong")
            from core.scheduler import add_scheduler_job

            def dummy():
                pass

            add_scheduler_job(dummy, "interval", 60, [], "failing job")
            args, kwargs = mock_log.error.call_args
            assert args == ("Failed to add a scheduler job",)
            assert kwargs["exc_info"] is mock_scheduler.add_job.side_effect
            assert kwargs["extra"]["description"] == "failing job"


class TestLockedSchedulerJobs:
    """Tests for cross-replica execution guards."""

    @patch("core.scheduler.platform_runtime")
    def test_sync_job_runs_when_lock_is_acquired(self, mock_runtime):
        from core.scheduler import run_locked_job

        mock_runtime.get_active_platform.return_value.lock.try_acquire.return_value.__enter__.return_value = True
        operation = MagicMock(return_value="done")

        assert run_locked_job("provider_sync", operation, 1) == "done"
        operation.assert_called_once_with(1)

    @patch("core.scheduler.platform_runtime")
    def test_sync_job_skips_when_lock_is_held(self, mock_runtime):
        from core.scheduler import run_locked_job

        mock_runtime.get_active_platform.return_value.lock.try_acquire.return_value.__enter__.return_value = False
        operation = MagicMock()

        assert run_locked_job("provider_sync", operation, 1) is None
        operation.assert_not_called()

    @patch("core.scheduler.platform_runtime")
    async def test_async_job_runs_when_lock_is_acquired(self, mock_runtime):
        from core.scheduler import _run_due_async_job

        mock_runtime.get_active_platform.return_value.lock.try_acquire.return_value.__enter__.return_value = True
        mock_runtime.get_active_platform.return_value.state = MemoryState()
        operation = AsyncMock(return_value="done")

        assert await _run_due_async_job("provider_async", 5, operation, 1) == "done"
        operation.assert_awaited_once_with(1)

    @patch("core.scheduler.platform_runtime")
    async def test_async_job_skips_when_lock_is_held(self, mock_runtime):
        from core.scheduler import _run_due_async_job

        mock_runtime.get_active_platform.return_value.lock.try_acquire.return_value.__enter__.return_value = False
        operation = AsyncMock()

        assert await _run_due_async_job("provider_async", 5, operation, 1) is None
        operation.assert_not_awaited()


class TestStopScheduler:
    """Tests for stop_scheduler."""

    def test_shuts_down_when_running(self):
        with patch("core.scheduler.scheduler") as mock_scheduler:
            mock_scheduler.running = True
            from core.scheduler import stop_scheduler

            stop_scheduler()
            mock_scheduler.shutdown.assert_called_once_with(wait=False)

    def test_skips_shutdown_when_not_running(self):
        with patch("core.scheduler.scheduler") as mock_scheduler:
            mock_scheduler.running = False
            from core.scheduler import stop_scheduler

            stop_scheduler()
            mock_scheduler.shutdown.assert_not_called()


def test_run_once_with_a_lock_runs_the_job_only_under_that_lock():
    import core.scheduler as core_scheduler

    with patch.object(core_scheduler.scheduler, "add_job") as add_job:
        core_scheduler.run_once(print, job_id="job", description="job", lock_name="lock")

    assert add_job.call_args.args[0] is core_scheduler.run_locked_job
    assert add_job.call_args.kwargs["args"] == ("lock", print)


class TestRunDueJob:
    """Every replica fires its own interval; a locked job still runs once per interval across them."""

    @staticmethod
    def _platform(state=None):
        platform = MagicMock()
        platform.lock.try_acquire.return_value.__enter__.return_value = True
        platform.state = state if state is not None else MemoryState()
        return platform

    def test_a_second_replica_inside_the_interval_skips(self):
        from core.scheduler import run_due_job

        operation = MagicMock(return_value="ran")
        with patch("core.scheduler.platform_runtime") as runtime:
            runtime.get_active_platform.return_value = self._platform()
            assert run_due_job("sweep", 5, operation, 1) == "ran"
            assert run_due_job("sweep", 5, operation, 1) is None

        operation.assert_called_once_with(1)

    def test_each_job_has_its_own_interval(self):
        from core.scheduler import run_due_job

        operation = MagicMock()
        with patch("core.scheduler.platform_runtime") as runtime:
            runtime.get_active_platform.return_value = self._platform()
            run_due_job("sweep", 5, operation)
            run_due_job("purge", 5, operation)

        assert operation.call_count == 2

    def test_the_mark_expires_before_this_replicas_next_tick(self):
        """Shorter than the interval, so the replica that ran is never blocked from its own next run."""
        from core.scheduler import run_due_job

        state = MagicMock()
        state.set_if_absent.return_value = True
        with patch("core.scheduler.platform_runtime") as runtime:
            runtime.get_active_platform.return_value = self._platform(state)
            run_due_job("sweep", 5, MagicMock())

        ttl = state.set_if_absent.call_args.args[2]
        assert 0 < ttl < 5 * 60

    def test_an_unreachable_state_store_still_runs_the_job_under_its_lock(self):
        from core.scheduler import run_due_job

        state = MagicMock()
        state.set_if_absent.side_effect = StateBackendUnavailableError("down")
        operation = MagicMock()
        with patch("core.scheduler.platform_runtime") as runtime:
            runtime.get_active_platform.return_value = self._platform(state)
            run_due_job("sweep", 5, operation)

        operation.assert_called_once_with()

    def test_another_replica_holding_the_lock_skips_without_marking(self):
        from core.scheduler import run_due_job

        platform = self._platform()
        platform.lock.try_acquire.return_value.__enter__.return_value = False
        operation = MagicMock()
        with patch("core.scheduler.platform_runtime") as runtime:
            runtime.get_active_platform.return_value = platform
            assert run_due_job("sweep", 5, operation) is None

        operation.assert_not_called()
        assert platform.state.get("endurain:scheduler:last-run:sweep") is None

    async def test_an_async_job_is_due_once_per_interval_too(self):
        from core.scheduler import _run_due_async_job

        operation = AsyncMock(return_value="ran")
        with patch("core.scheduler.platform_runtime") as runtime:
            runtime.get_active_platform.return_value = self._platform()
            assert await _run_due_async_job("sync", 5, operation) == "ran"
            assert await _run_due_async_job("sync", 5, operation) is None

        operation.assert_awaited_once()
