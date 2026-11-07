"""Tests for the known-device prune job."""

from unittest.mock import patch

import module_registry as runtime_module_registry
import modules.auth.known_devices.scheduled_jobs as known_devices_scheduled_jobs


def test_the_prune_runs_daily_under_its_lock():
    (job,) = known_devices_scheduled_jobs.recurring_jobs()

    assert job.func is known_devices_scheduled_jobs.delete_unseen_devices
    assert job.minutes == 1440
    assert job.lock_name == known_devices_scheduled_jobs.PRUNE_LOCK_NAME


def test_the_prune_is_registered_with_the_runtime():
    module = next(module for module in runtime_module_registry.MODULES if module.name == "known_devices")

    assert module.recurring_jobs is known_devices_scheduled_jobs.recurring_jobs


@patch("modules.auth.known_devices.scheduled_jobs.known_devices_service.delete_unseen_devices", return_value=3)
@patch("modules.auth.known_devices.scheduled_jobs.core_database.SessionLocal")
def test_the_prune_deletes_in_its_own_session(session_local, delete_unseen_devices):
    known_devices_scheduled_jobs.delete_unseen_devices()

    db = session_local.return_value.__enter__.return_value
    assert delete_unseen_devices.call_args.args[1] is db
    session_local.return_value.__exit__.assert_called_once()
