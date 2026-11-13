"""Tests for the scheduled purge of revoked and expired API keys."""

from datetime import UTC, datetime, timedelta
from unittest.mock import patch

import module_registry as runtime_module_registry
import modules.auth.api_keys.constants as api_keys_constants
import modules.auth.api_keys.scheduled_jobs as api_keys_jobs
import modules.auth.api_keys.service as api_keys_service


def test_the_retention_is_30_days():
    assert timedelta(days=30) == api_keys_constants.STALE_API_KEY_RETENTION


def test_the_service_purges_keys_older_than_the_retention(mock_db):
    with patch.object(api_keys_service.api_keys_crud, "delete_stale_api_keys", side_effect=[3]) as delete:
        before = datetime.now(UTC)
        assert api_keys_service.delete_stale_api_keys(mock_db) == 3

    cutoff, _limit, db = delete.call_args.args
    assert (
        before - api_keys_constants.STALE_API_KEY_RETENTION
        <= cutoff
        <= datetime.now(UTC) - (api_keys_constants.STALE_API_KEY_RETENTION)
    )
    assert db is mock_db
    mock_db.commit.assert_called_once()


@patch("modules.auth.api_keys.scheduled_jobs.core_database")
@patch("modules.auth.api_keys.scheduled_jobs.api_keys_service")
def test_the_job_runs_the_service_in_its_own_session(mock_service, mock_database):
    mock_service.delete_stale_api_keys.return_value = 2

    api_keys_jobs.delete_stale_api_keys_from_db()

    mock_service.delete_stale_api_keys.assert_called_once_with(mock_database.SessionLocal.return_value.__enter__())


def test_the_purge_is_a_recurring_job_holding_a_distributed_lock():
    module = next(module for module in runtime_module_registry.MODULES if module.name == "api_keys")
    jobs = module.recurring_jobs()
    assert [job.lock_name for job in jobs] == [api_keys_jobs.PURGE_LOCK_NAME]
    assert jobs[0].func is api_keys_jobs.delete_stale_api_keys_from_db
