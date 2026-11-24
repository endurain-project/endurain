"""The startup task that issues the first-run setup token."""

import logging

import jasil.runtime as platform_runtime

import modules.auth.onboarding.scheduled_jobs as onboarding_scheduled_jobs
import modules.auth.onboarding.token_store as onboarding_token_store
from tests._factories.users import make_user


def _setup_tokens(caplog) -> list[logging.LogRecord]:
    return [record for record in caplog.records if hasattr(record, "setup_token")]


def test_with_no_account_it_mints_a_valid_token_and_tells_the_operator(db, caplog):
    with caplog.at_level(logging.WARNING):
        onboarding_scheduled_jobs.issue_onboarding_token_if_needed()

    (record,) = _setup_tokens(caplog)
    assert record.levelno == logging.WARNING
    assert record.console is True
    assert record.setup_token not in record.getMessage()
    assert onboarding_token_store.OnboardingTokenStore(platform_runtime.get_state()).exists(record.setup_token)


def test_with_an_account_it_mints_and_logs_nothing(db, caplog):
    make_user(db)

    with caplog.at_level(logging.DEBUG):
        onboarding_scheduled_jobs.issue_onboarding_token_if_needed()

    assert _setup_tokens(caplog) == []
    assert list(platform_runtime.get_state().iter_keys("endurain:auth:onboarding:")) == []
