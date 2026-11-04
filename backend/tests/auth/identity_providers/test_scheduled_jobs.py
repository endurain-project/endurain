"""Scheduled work owned by identity providers runs on one replica at a time."""

from unittest.mock import patch

import modules.auth.identity_providers.scheduled_jobs as idp_scheduled_jobs


def test_the_icon_sweep_holds_its_own_distributed_lock():
    jobs = idp_scheduled_jobs.recurring_jobs()

    assert [job.lock_name for job in jobs] == [idp_scheduled_jobs.ICON_SWEEP_LOCK_NAME]
    assert jobs[0].func is idp_scheduled_jobs.sweep_unreferenced_icons


@patch("modules.auth.identity_providers.scheduled_jobs.idp_icon_service.sweep_unreferenced_icons")
@patch("modules.auth.identity_providers.scheduled_jobs.platform_runtime")
def test_the_icon_sweep_resolves_storage_at_the_entry_point(mock_runtime, mock_sweep):
    idp_scheduled_jobs.sweep_unreferenced_icons()

    mock_sweep.assert_called_once_with(mock_runtime.get_active_platform.return_value.storage)
