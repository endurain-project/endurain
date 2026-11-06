"""A new API key expires within the server's maximum API key lifetime."""

from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock, patch

import pytest
from fastapi.exceptions import RequestValidationError

import modules.auth.account_security.dependencies as account_security_dependencies
import modules.auth.api_keys.schema as api_keys_schema
import modules.server_settings.contracts as server_settings_contracts

_MAX = timedelta(days=365)


@pytest.fixture
def policy(session_policy):
    with patch.object(
        account_security_dependencies.server_settings_integration,
        "get_session_policy",
        return_value=server_settings_contracts.SessionPolicy(
            access_token_ttl=session_policy.access_token_ttl,
            refresh_token_ttl=session_policy.refresh_token_ttl,
            idle_timeout=session_policy.idle_timeout,
            absolute_timeout=session_policy.absolute_timeout,
            api_key_max_lifetime=_MAX,
        ),
    ):
        yield


def _create(expires_at: datetime | None) -> api_keys_schema.UserApiKeyCreate:
    return api_keys_schema.UserApiKeyCreate(
        step_up={"current_password": "pw"}, name="CLI", scopes=["activities:upload"], expires_at=expires_at
    )


@pytest.mark.usefixtures("policy")
class TestApiKeyExpiry:
    def test_an_omitted_expiry_is_the_maximum_lifetime(self):
        before = datetime.now(UTC)
        expiry = account_security_dependencies.api_key_expiry(_create(None), MagicMock())

        assert before + _MAX <= expiry <= datetime.now(UTC) + _MAX

    def test_an_expiry_within_the_maximum_is_kept(self):
        requested = datetime.now(UTC) + timedelta(days=30)

        assert account_security_dependencies.api_key_expiry(_create(requested), MagicMock()) == requested

    def test_an_expiry_beyond_the_maximum_is_a_field_error_on_expires_at(self):
        with pytest.raises(RequestValidationError) as exc_info:
            account_security_dependencies.api_key_expiry(
                _create(datetime.now(UTC) + _MAX + timedelta(days=1)), MagicMock()
            )

        assert exc_info.value.errors()[0]["loc"] == ("body", "expires_at")

    def test_a_past_expiry_is_still_refused_by_the_schema(self):
        with pytest.raises(ValueError, match="expires_at"):
            _create(datetime.now(UTC) - timedelta(days=1))
