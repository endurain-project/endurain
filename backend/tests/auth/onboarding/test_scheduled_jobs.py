"""Tests for the startup task that issues the first-run setup token."""

import logging
from unittest.mock import MagicMock, patch

import pytest
from jasil.backends.state_memory import MemoryState

import core.logger as core_logger
import modules.auth.onboarding.scheduled_jobs as onboarding_scheduled_jobs
import modules.auth.onboarding.token_store as onboarding_token_store

_USERS = "modules.auth.onboarding.scheduled_jobs.users_integration"


@pytest.fixture
def state():
    memory = MemoryState()
    with (
        patch("modules.auth.onboarding.scheduled_jobs.platform_runtime.get_state", return_value=memory),
        patch("modules.auth.onboarding.scheduled_jobs.core_database.SessionLocal") as session_local,
    ):
        session_local.return_value.__enter__.return_value = MagicMock()
        yield memory


@patch(_USERS)
def test_with_no_account_it_mints_a_valid_token_and_tells_the_operator(users, state, caplog):
    users.any_user_exists.return_value = False

    with caplog.at_level(logging.WARNING, logger=core_logger.get_logger(onboarding_scheduled_jobs.__name__).name):
        onboarding_scheduled_jobs.issue_onboarding_token_if_needed()

    records = [r for r in caplog.records if hasattr(r, "setup_token")]
    assert len(records) == 1
    record = records[0]
    assert record.levelno == logging.WARNING
    assert record.console is True
    assert "setup_token" not in record.getMessage() and record.setup_token not in record.getMessage()
    assert onboarding_token_store.OnboardingTokenStore(state).exists(record.setup_token)


@patch(_USERS)
def test_with_an_account_it_mints_and_logs_nothing(users, state, caplog):
    users.any_user_exists.return_value = True

    with caplog.at_level(logging.DEBUG):
        onboarding_scheduled_jobs.issue_onboarding_token_if_needed()

    assert not [r for r in caplog.records if r.name.endswith("onboarding.scheduled_jobs")]
    assert list(state.iter_keys("endurain:auth:onboarding:")) == []
