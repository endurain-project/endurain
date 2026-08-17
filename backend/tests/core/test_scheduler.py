"""Tests for core.scheduler — APScheduler setup and lifecycle."""

from unittest.mock import patch


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
            import infra.retention as platform_retention
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
            mock_log.error.assert_any_call(
                "Failed to add scheduler job to failing job: ValueError", exc_info=mock_scheduler.add_job.side_effect
            )


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
