"""Scheduled work owned by users runs on one replica at a time."""

from unittest.mock import patch

import modules.users.users.scheduled_jobs as users_scheduled_jobs


def test_each_job_holds_its_own_distributed_lock():
    locks = [job.lock_name for job in users_scheduled_jobs.recurring_jobs()]
    assert len(locks) == 2
    assert all(locks)
    assert len(set(locks)) == len(locks)


@patch("modules.users.users.scheduled_jobs.users_photo_service.sweep_unreferenced_photos")
@patch("modules.users.users.scheduled_jobs.platform_runtime")
def test_the_photo_sweep_resolves_storage_at_the_entry_point(mock_runtime, mock_sweep):
    users_scheduled_jobs.sweep_unreferenced_photos()

    mock_sweep.assert_called_once_with(mock_runtime.get_active_platform.return_value.storage)
