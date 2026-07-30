"""Tests for the durable-job worker loop."""

from unittest.mock import MagicMock

import infra.jobs.worker as jobs_worker
from infra.jobs.runner import JobRunner


class TestRunWorker:
    def test_drains_until_stop(self):
        stop = MagicMock()
        stop.is_set.side_effect = [False, False, False, True]
        runner = MagicMock(spec=JobRunner)
        runner.run_once.return_value = 1  # work found -> loop immediately, no wait
        jobs_worker.run_worker(runner, poll_interval_seconds=0.5, stop=stop)
        assert runner.run_once.call_count == 3
        stop.wait.assert_not_called()

    def test_waits_poll_interval_when_idle(self):
        stop = MagicMock()
        stop.is_set.side_effect = [False, True]
        runner = MagicMock(spec=JobRunner)
        runner.run_once.return_value = 0  # empty -> wait one poll interval
        jobs_worker.run_worker(runner, poll_interval_seconds=0.5, stop=stop)
        stop.wait.assert_called_once_with(0.5)

    def test_survives_iteration_error(self):
        stop = MagicMock()
        stop.is_set.side_effect = [False, True]
        runner = MagicMock(spec=JobRunner)
        runner.run_once.side_effect = RuntimeError("boom")
        jobs_worker.run_worker(runner, poll_interval_seconds=0.25, stop=stop)  # does not raise
        stop.wait.assert_called_once_with(0.25)


class TestBackgroundWorker:
    def test_start_is_idempotent_and_stop_joins(self):
        runner = MagicMock(spec=JobRunner)
        runner.run_once.return_value = 0  # idle: the loop blocks in stop.wait until stopped
        worker = jobs_worker.BackgroundWorker(runner, poll_interval_seconds=10)
        worker.start()
        thread = worker._thread
        worker.start()  # idempotent: no second thread
        assert worker._thread is thread
        assert thread is not None
        assert thread.is_alive()
        worker.stop()
        assert worker._thread is None
        assert not thread.is_alive()

    def test_stop_without_start_is_safe(self):
        worker = jobs_worker.BackgroundWorker(MagicMock(spec=JobRunner), poll_interval_seconds=1)
        worker.stop()  # no thread to join
        assert worker._thread is None
