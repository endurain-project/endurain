"""Tests for the per-user cap on active API keys."""

from datetime import UTC, datetime
from unittest.mock import MagicMock, patch

import core.exceptions as core_exceptions
import modules.auth.account_security.api_key_service as api_key_service
import modules.auth.api_keys.constants as api_keys_constants
import modules.auth.api_keys.schema as api_keys_schema
from tests._helpers.auth import MOCK_USER_ID


def _data():
    return api_keys_schema.UserApiKeyCreate(name="k", scopes=["activities:upload"], step_up={"current_password": "pw"})


def test_the_cap_is_25_active_keys():
    assert api_keys_constants.MAX_ACTIVE_API_KEYS_PER_USER == 25


def _create(mock_db, counts):
    """Run a creation whose successive active-key counts are ``counts``; return the patched collaborators."""
    with (
        patch.object(api_key_service.step_up_service, "verify_step_up_credentials") as step_up,
        patch.object(api_key_service.users_integration, "require_user"),
        patch.object(api_key_service.api_keys_integration, "count_active_api_keys", side_effect=counts),
        patch.object(api_key_service.api_keys_integration, "lock_api_key_creation") as lock,
        patch.object(api_key_service.api_keys_integration, "create_api_key") as create,
        patch.object(api_key_service.account_security_event_publishers, "publish_account_security_changed"),
        patch.object(api_key_service, "_stage_key_audit"),
        patch.object(api_key_service.api_keys_schema, "UserApiKeyCreatedRead", return_value="created"),
    ):
        result = None
        error = None
        try:
            result = api_key_service.create_user_api_key(
                MOCK_USER_ID, "sid", _data(), datetime.now(UTC), MagicMock(), mock_db
            )
        except core_exceptions.ApiKeyLimitError as err:
            error = err
    return step_up, lock, create, result, error


def test_a_user_at_the_cap_gets_a_conflict_and_nothing_is_created_nor_step_up_spent(mock_db):
    cap = api_keys_constants.MAX_ACTIVE_API_KEYS_PER_USER
    step_up, lock, create, _, error = _create(mock_db, [cap])

    assert error is not None and error.status_code == 409
    step_up.assert_not_called()
    lock.assert_not_called()
    create.assert_not_called()
    mock_db.commit.assert_not_called()


def test_a_user_one_below_the_cap_may_create_a_key(mock_db):
    below = api_keys_constants.MAX_ACTIVE_API_KEYS_PER_USER - 1
    assert below == 24
    step_up, lock, create, result, error = _create(mock_db, [below, below])

    assert error is None and result is not None
    step_up.assert_called_once()
    lock.assert_called_once()
    create.assert_called_once()
    mock_db.commit.assert_called_once()


def test_a_key_created_meanwhile_is_caught_by_the_count_under_the_lock(mock_db):
    cap = api_keys_constants.MAX_ACTIVE_API_KEYS_PER_USER
    _, lock, create, _, error = _create(mock_db, [cap - 1, cap])

    assert error is not None
    lock.assert_called_once()
    create.assert_not_called()
    mock_db.commit.assert_not_called()


def test_the_conflict_has_its_own_problem_type():
    assert issubclass(core_exceptions.ApiKeyLimitError, core_exceptions.ConflictError)
    assert core_exceptions.ApiKeyLimitError.code == "api-key-limit"
