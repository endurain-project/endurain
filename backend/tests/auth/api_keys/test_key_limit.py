"""Tests for the per-user cap on active API keys."""

from datetime import UTC, datetime
from unittest.mock import MagicMock, patch

import pytest

import core.exceptions as core_exceptions
import modules.auth.account_security.api_key_service as api_key_service
import modules.auth.api_keys.constants as api_keys_constants
import modules.auth.api_keys.schema as api_keys_schema
from tests._helpers.auth import MOCK_USER_ID


def _data():
    return api_keys_schema.UserApiKeyCreate(name="k", scopes=["activities:upload"], step_up={"current_password": "pw"})


def test_the_cap_is_25_active_keys():
    assert api_keys_constants.MAX_ACTIVE_API_KEYS_PER_USER == 25


def test_a_user_at_the_cap_gets_a_conflict_and_nothing_is_created(mock_db):
    with (
        patch.object(api_key_service.step_up_service, "verify_step_up_credentials"),
        patch.object(api_key_service.users_integration, "require_user"),
        patch.object(
            api_key_service.api_keys_integration,
            "count_active_api_keys",
            return_value=api_keys_constants.MAX_ACTIVE_API_KEYS_PER_USER,
        ),
        patch.object(api_key_service.api_keys_integration, "create_api_key") as create,
        pytest.raises(core_exceptions.ApiKeyLimitError) as raised,
    ):
        api_key_service.create_user_api_key(MOCK_USER_ID, "sid", _data(), datetime.now(UTC), MagicMock(), mock_db)

    assert raised.value.status_code == 409
    create.assert_not_called()
    mock_db.commit.assert_not_called()


def test_the_conflict_has_its_own_problem_type():
    assert issubclass(core_exceptions.ApiKeyLimitError, core_exceptions.ConflictError)
    assert core_exceptions.ApiKeyLimitError.code == "api-key-limit"
