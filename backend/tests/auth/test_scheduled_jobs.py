"""Auth runtime contributions declare recurring and startup maintenance."""

from unittest.mock import MagicMock, patch

import pytest

import module_registry as runtime_module_registry
import modules.auth.sign_up_tokens.scheduled_jobs as sign_up_jobs


def test_auth_runtime_modules_are_registered():
    names = {module.name for module in runtime_module_registry.MODULES}
    assert {
        "oauth_state",
        "sessions",
        "rotated_refresh_tokens",
        "password_reset_tokens",
        "sign_up_tokens",
    } <= names


def test_token_purges_are_startup_tasks():
    modules = {module.name: module for module in runtime_module_registry.MODULES}
    for name in ("oauth_state", "password_reset_tokens", "sign_up_tokens"):
        assert modules[name].startup_tasks


@pytest.mark.parametrize("module_name", ["oauth_state", "password_reset_tokens", "sign_up_tokens"])
def test_startup_purges_hold_a_distributed_lock(module_name):
    module = next(module for module in runtime_module_registry.MODULES if module.name == module_name)
    assert module.startup_tasks
    assert all(task.lock_name for task in module.startup_tasks)


def test_startup_purges_share_the_lock_of_their_recurring_job():
    for name in ("oauth_state", "password_reset_tokens", "sign_up_tokens"):
        module = next(module for module in runtime_module_registry.MODULES if module.name == name)
        assert {task.lock_name for task in module.startup_tasks} == {job.lock_name for job in module.recurring_jobs()}


def test_startup_task_without_a_lock_runs_directly():
    func = MagicMock()
    runtime_module_registry.StartupTask("task", "Running task", func).run()
    func.assert_called_once_with()


@patch("core.scheduler.platform_runtime")
def test_startup_task_with_a_lock_runs_when_the_lock_is_acquired(mock_runtime):
    mock_runtime.get_active_platform.return_value.lock.try_acquire.return_value.__enter__.return_value = True
    func = MagicMock()
    runtime_module_registry.StartupTask("task", "Running task", func, lock_name="lock").run()
    func.assert_called_once_with()


@patch("core.scheduler.platform_runtime")
def test_startup_task_with_a_lock_skips_when_another_replica_holds_it(mock_runtime):
    mock_runtime.get_active_platform.return_value.lock.try_acquire.return_value.__enter__.return_value = False
    func = MagicMock()
    runtime_module_registry.StartupTask("task", "Running task", func, lock_name="lock").run()
    func.assert_not_called()


def _recurring_jobs(module_name: str):
    module = next(module for module in runtime_module_registry.MODULES if module.name == module_name)
    return module.recurring_jobs()


@pytest.mark.parametrize(
    "module_name",
    [
        "oauth_state",
        "rotated_refresh_tokens",
        "password_reset_tokens",
        "sign_up_tokens",
        "sessions",
    ],
)
def test_cleanup_jobs_hold_a_distributed_lock(module_name):
    jobs = _recurring_jobs(module_name)
    assert jobs
    assert all(job.lock_name for job in jobs)


def test_mfa_has_no_recurring_job():
    mfa = next(module for module in runtime_module_registry.MODULES if module.name == "mfa")
    assert mfa.recurring_jobs is None


def test_cleanup_job_lock_names_are_distinct():
    names = [
        job.lock_name
        for module_name in (
            "oauth_state",
            "rotated_refresh_tokens",
            "password_reset_tokens",
            "sign_up_tokens",
            "sessions",
        )
        for job in _recurring_jobs(module_name)
    ]
    assert len(names) == len(set(names))


def test_reencrypt_startup_tasks_hold_distinct_locks():
    locks = [
        task.lock_name
        for module in runtime_module_registry.MODULES
        for task in module.startup_tasks
        if task.name.startswith("reencrypt_")
    ]

    assert len(locks) == 6
    assert all(locks)
    assert len(set(locks)) == len(locks)


def test_the_unverified_sign_up_purge_is_an_hourly_job_with_its_own_lock_and_startup_task():
    module = next(module for module in runtime_module_registry.MODULES if module.name == "sign_up_tokens")
    jobs = {job.func.__name__: job for job in module.recurring_jobs()}
    purge = jobs["delete_unverified_sign_ups_from_db"]

    assert purge.minutes == 60
    assert purge.lock_name == "auth_unverified_sign_ups_purge"
    assert purge.lock_name != jobs["delete_expired_tokens_from_db"].lock_name
    assert any(
        task.name == "purge_unverified_sign_ups" and task.lock_name == purge.lock_name for task in module.startup_tasks
    )


@patch("modules.auth.sign_up_tokens.scheduled_jobs.sign_up_service.purge_unverified_sign_ups", return_value=2)
@patch("modules.auth.sign_up_tokens.scheduled_jobs.core_database.SessionLocal")
def test_the_unverified_sign_up_purge_job_runs_the_service_in_its_own_session(mock_session_local, mock_purge):
    sign_up_jobs.delete_unverified_sign_ups_from_db()

    mock_purge.assert_called_once_with(mock_session_local.return_value.__enter__.return_value)
