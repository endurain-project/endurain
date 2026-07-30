"""Tests for the durable-job wiring service — worker lifecycle and scheduled maintenance."""

from unittest.mock import MagicMock, patch

import pytest

import infra.jobs.service as jobs_service


@pytest.fixture(autouse=True)
def _reset_worker():
    jobs_service._worker = None
    yield
    jobs_service._worker = None


def _platform():
    return MagicMock()


class TestBuildRunner:
    @patch("infra.jobs.service.JobRunner")
    @patch("infra.jobs.service.core_config")
    @patch("infra.jobs.service.platform_runtime")
    def test_builds_runner_from_settings(self, mock_runtime, mock_config, mock_runner):
        platform = MagicMock()
        mock_runtime.get_active_platform.return_value = platform
        mock_config.settings.JOBS_LEASE_SECONDS = 300
        mock_config.settings.JOBS_BATCH_SIZE = 10
        mock_config.settings.JOBS_BACKOFF_BASE_SECONDS = 5.0
        mock_config.settings.JOBS_BACKOFF_MAX_SECONDS = 3600.0

        jobs_service.build_runner()

        kwargs = mock_runner.call_args.kwargs
        assert kwargs["clock"] is platform.clock
        assert kwargs["lease_seconds"] == 300
        assert kwargs["batch_size"] == 10
        assert kwargs["backoff_base_seconds"] == 5.0
        assert kwargs["backoff_max_seconds"] == 3600.0
        assert isinstance(kwargs["worker_id"], str)


class TestWorkerLifecycle:
    @patch("infra.jobs.service.BackgroundWorker")
    @patch("infra.jobs.service.build_runner")
    @patch("infra.jobs.service.core_config")
    def test_start_is_idempotent(self, mock_config, mock_build, mock_worker_cls):
        mock_config.settings.JOBS_POLL_INTERVAL_SECONDS = 2.0
        jobs_service.start_job_worker()
        jobs_service.start_job_worker()
        mock_worker_cls.assert_called_once()
        mock_worker_cls.return_value.start.assert_called_once()

    @patch("infra.jobs.service.BackgroundWorker")
    @patch("infra.jobs.service.build_runner")
    @patch("infra.jobs.service.core_config")
    def test_stop_stops_and_clears(self, mock_config, mock_build, mock_worker_cls):
        mock_config.settings.JOBS_POLL_INTERVAL_SECONDS = 2.0
        jobs_service.start_job_worker()
        worker = mock_worker_cls.return_value
        jobs_service.stop_job_worker()
        worker.stop.assert_called_once()
        assert jobs_service._worker is None

    def test_stop_without_start_is_safe(self):
        jobs_service.stop_job_worker()  # no worker running
        assert jobs_service._worker is None


class TestRelayScheduled:
    @patch("infra.jobs.service.jobs_relay")
    @patch("infra.jobs.service.core_config")
    @patch("infra.jobs.service.platform_runtime")
    def test_drains_until_empty(self, mock_runtime, mock_config, mock_relay):
        mock_runtime.get_active_platform.return_value = _platform()
        mock_relay.relay_outbox_once.side_effect = [3, 0]  # drain two batches then stop

        jobs_service.relay_outbox_scheduled()

        assert mock_relay.relay_outbox_once.call_count == 2

    @patch("infra.jobs.service.jobs_relay")
    @patch("infra.jobs.service.core_config")
    @patch("infra.jobs.service.platform_runtime")
    def test_stops_after_bounded_batches(self, mock_runtime, mock_config, mock_relay):
        mock_runtime.get_active_platform.return_value = _platform()
        mock_relay.relay_outbox_once.return_value = 10  # always full: bounded by _MAX_RELAY_BATCHES

        jobs_service.relay_outbox_scheduled()

        assert mock_relay.relay_outbox_once.call_count == jobs_service._MAX_RELAY_BATCHES


class TestReapScheduled:
    @patch("infra.jobs.service.core_database")
    @patch("infra.jobs.service.jobs_crud")
    @patch("infra.jobs.service.platform_runtime")
    def test_reclaims_expired_leases(self, mock_runtime, mock_crud, mock_db):
        mock_runtime.get_active_platform.return_value = _platform()
        mock_crud.reclaim_expired_leases.return_value = 2

        jobs_service.reap_expired_jobs_scheduled()

        mock_crud.reclaim_expired_leases.assert_called_once()


class TestScheduleJobMaintenance:
    def test_registers_relay_and_reaper(self):
        scheduler = MagicMock()
        jobs_service.schedule_job_maintenance(scheduler)
        assert scheduler.add_job.call_count == 2
        job_ids = {call.kwargs["id"] for call in scheduler.add_job.call_args_list}
        assert job_ids == {"endurain_outbox_relay", "endurain_job_reaper"}
