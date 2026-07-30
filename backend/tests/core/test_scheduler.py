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

    def test_adds_all_recurring_jobs(self):
        with (
            patch("core.scheduler.scheduler") as mock_scheduler,
            patch("core.scheduler.add_scheduler_job") as mock_add_job,
        ):
            mock_scheduler.running = False
            from core.scheduler import start_scheduler

            start_scheduler()
            assert mock_add_job.call_count == 16

    def test_idp_link_token_cleanup_job_registered(self):
        """IdP link token cleanup must be registered with a 5-minute interval."""
        import modules.auth.identity_providers.link_tokens.utils as idp_link_tokens_utils

        with (
            patch("core.scheduler.scheduler") as mock_scheduler,
            patch("core.scheduler.add_scheduler_job") as mock_add_job,
        ):
            mock_scheduler.running = False
            from core.scheduler import start_scheduler

            start_scheduler()

        calls = [(call.args[0], call.args[1], call.args[2], call.args[4]) for call in mock_add_job.call_args_list]
        assert any(
            func is idp_link_tokens_utils.delete_idp_link_expired_tokens_from_db
            and trigger == "interval"
            and minutes == 5
            and "idp link token" in description.lower()
            for func, trigger, minutes, description in calls
        ), "IdP link token cleanup job not found or mis-configured"


class TestAddSchedulerJob:
    """Tests for add_scheduler_job."""

    def test_adds_job_successfully(self):
        with (
            patch("core.scheduler.scheduler") as mock_scheduler,
            patch("core.scheduler.core_logger.print_to_log") as mock_log,
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
            mock_log.assert_called_once()

    def test_logs_error_when_add_job_fails(self):
        with (
            patch("core.scheduler.scheduler") as mock_scheduler,
            patch("core.scheduler.core_logger.print_to_log") as mock_log,
        ):
            mock_scheduler.add_job.side_effect = ValueError("something went wrong")
            from core.scheduler import add_scheduler_job

            def dummy():
                pass

            add_scheduler_job(dummy, "interval", 60, [], "failing job")
            mock_log.assert_any_call(
                "Failed to add scheduler job to failing job: ValueError",
                "error",
                exc=mock_scheduler.add_job.side_effect,
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
