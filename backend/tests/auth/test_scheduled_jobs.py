"""Auth runtime contributions declare recurring and startup maintenance."""

import pytest

import module_registry as runtime_module_registry


def test_auth_runtime_modules_are_registered():
    names = {module.name for module in runtime_module_registry.MODULES}
    assert {
        "oauth_state",
        "sessions",
        "rotated_refresh_tokens",
        "mfa",
        "identity_provider_link_tokens",
        "password_reset_tokens",
        "sign_up_tokens",
    } <= names


def test_token_purges_are_startup_tasks():
    modules = {module.name: module for module in runtime_module_registry.MODULES}
    for name in ("oauth_state", "identity_provider_link_tokens", "password_reset_tokens", "sign_up_tokens"):
        assert modules[name].startup_tasks


def _recurring_jobs(module_name: str):
    module = next(module for module in runtime_module_registry.MODULES if module.name == module_name)
    return module.recurring_jobs()


@pytest.mark.parametrize(
    "module_name",
    [
        "oauth_state",
        "rotated_refresh_tokens",
        "mfa",
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


def test_cleanup_job_lock_names_are_distinct():
    names = [
        job.lock_name
        for module_name in (
            "oauth_state",
            "rotated_refresh_tokens",
            "mfa",
            "identity_provider_link_tokens",
            "password_reset_tokens",
            "sign_up_tokens",
            "sessions",
        )
        for job in _recurring_jobs(module_name)
    ]
    assert len(names) == len(set(names))
