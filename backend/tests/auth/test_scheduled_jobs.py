"""Auth runtime contributions declare recurring and startup maintenance."""

from unittest.mock import MagicMock, patch

import pytest

import module_registry as runtime_module_registry


def test_auth_runtime_modules_are_registered():
    names = {module.name for module in runtime_module_registry.MODULES}
    assert {
        "oauth_state",
        "sessions",
        "rotated_refresh_tokens",
        "identity_provider_link_tokens",
        "password_reset_tokens",
        "sign_up_tokens",
    } <= names


def test_token_purges_are_startup_tasks():
    modules = {module.name: module for module in runtime_module_registry.MODULES}
    for name in ("oauth_state", "identity_provider_link_tokens", "password_reset_tokens", "sign_up_tokens"):
        assert modules[name].startup_tasks


@pytest.mark.parametrize(
    "module_name", ["oauth_state", "identity_provider_link_tokens", "password_reset_tokens", "sign_up_tokens"]
)
def test_startup_purges_hold_a_distributed_lock(module_name):
    module = next(module for module in runtime_module_registry.MODULES if module.name == module_name)
    assert module.startup_tasks
    assert all(task.lock_name for task in module.startup_tasks)


def test_startup_purges_share_the_lock_of_their_recurring_job():
    for name in ("oauth_state", "identity_provider_link_tokens", "password_reset_tokens", "sign_up_tokens"):
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
        "identity_provider_link_tokens",
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
    assert "mfa" not in {module.name for module in runtime_module_registry.MODULES}


def test_cleanup_job_lock_names_are_distinct():
    names = [
        job.lock_name
        for module_name in (
            "oauth_state",
            "rotated_refresh_tokens",
            "identity_provider_link_tokens",
            "password_reset_tokens",
            "sign_up_tokens",
            "sessions",
        )
        for job in _recurring_jobs(module_name)
    ]
    assert len(names) == len(set(names))
