"""Every flow that sets a password refuses a breached one when the check is on, before it stages any write."""

from contextlib import contextmanager
from unittest.mock import MagicMock, patch

import pytest
from jasil.backends.state_memory import MemoryState

import modules.auth.account_security.account_security_service as account_security_service
import modules.auth.authentication.schema as authentication_schema
import modules.auth.credentials.contracts as credentials_contracts
import modules.auth.credentials.service as credentials_service
import modules.auth.onboarding.schema as onboarding_schema
import modules.auth.onboarding.service as onboarding_service
import modules.auth.onboarding.token_store as onboarding_token_store
import modules.auth.password_reset_tokens.service as password_reset_service
import modules.auth.sign_up_tokens.service as sign_up_service
import modules.users.users.schema as users_schema
import modules.users.users.service as users_service
import modules.users.users_profile.service as users_profile_service

_PASSWORD = "a-password-that-leaked-somewhere"


class _ReachedError(Exception):
    """Raised by the first step after the breach check, to show the flow got past it."""


def _settings(enabled: bool) -> MagicMock:
    return MagicMock(
        password_breach_check_enabled=enabled, signup_enabled=True, signup_require_email_verification=False
    )


@contextmanager
def _breach(enabled: bool, *, breached: bool = True):
    with patch.object(credentials_service.credentials_password_breach, "is_breached", return_value=breached) as check:
        yield check, _settings(enabled)


def _reset(settings, db):
    with (
        patch.object(password_reset_service.server_settings_integration, "get_server_settings", return_value=settings),
        patch.object(
            password_reset_service.password_reset_crud, "claim_password_reset_token", side_effect=_ReachedError
        ),
    ):
        password_reset_service.use_password_reset_token("token", _PASSWORD, db)


def _verify_email(settings, db):
    with (
        patch.object(sign_up_service.server_settings_integration, "get_server_settings", return_value=settings),
        patch.object(sign_up_service, "verify_sign_up_token", side_effect=_ReachedError),
    ):
        sign_up_service.verify_email("token", _PASSWORD, db)


def _signup(settings, db):
    user = users_schema.UserSignup(
        name="Test", username="testuser", email="test@example.com", password=_PASSWORD, preferred_language="en"
    )
    with (
        patch.object(sign_up_service.server_settings_integration, "get_server_settings", return_value=settings),
        patch.object(sign_up_service.users_integration, "stage_signup_user", side_effect=_ReachedError),
    ):
        sign_up_service.signup(user, MemoryState(), db)


def _onboarding(settings, db):
    store = onboarding_token_store.OnboardingTokenStore(MemoryState())
    request = onboarding_schema.OnboardingCreate(
        token=store.issue(), name="Owner", username="owner", email="owner@example.com", password=_PASSWORD
    )
    with (
        patch.object(onboarding_service.users_integration, "any_user_exists", return_value=False),
        patch.object(onboarding_service.users_integration, "stage_first_admin", side_effect=_ReachedError),
        patch.object(onboarding_service.server_settings_integration, "get_server_settings", return_value=settings),
    ):
        onboarding_service.complete_onboarding(request, store, db)


def _admin_create(settings, db):
    user = users_schema.UserCreate(
        name="N", username="n", email="n@example.com", active=True, access_type="admin", password=_PASSWORD
    )
    with (
        patch.object(users_service.server_settings_integration, "get_server_settings", return_value=settings),
        patch.object(users_service.account_security_integration, "verify_step_up", side_effect=_ReachedError),
    ):
        users_service.create_user(user, None, 9, "sid-9", MagicMock(), db)


def _admin_set_password(settings, db):
    attributes = users_schema.UserAdminEditPassword(password=_PASSWORD, step_up={"current_password": "admin-password"})
    with (
        patch.object(users_service.server_settings_integration, "get_server_settings", return_value=settings),
        patch.object(users_service.account_security_integration, "verify_step_up", side_effect=_ReachedError),
    ):
        users_service.change_user_password(4, attributes, 9, "sid-9", MagicMock(), db)


def _own_change(settings, db):
    change = users_schema.UserEditPassword(password=_PASSWORD, step_up={"current_password": "current"})
    with (
        patch.object(users_profile_service.server_settings_integration, "get_server_settings", return_value=settings),
        patch.object(
            users_profile_service.account_security_integration, "change_own_password", side_effect=_ReachedError
        ),
    ):
        users_profile_service.change_password(7, change, "sid", MagicMock(), db)


def _required_change(settings, db):
    store = MagicMock()
    store.get.return_value = MagicMock(user_id=7, client_type="web", security_generation=0)
    request = authentication_schema.PasswordChangeLoginRequest(password_change_challenge="c" * 43, password=_PASSWORD)
    with (
        patch.object(account_security_service.users_integration, "get_user", return_value=MagicMock(id=7)),
        patch.object(account_security_service.users_integration, "require_active_user"),
        patch.object(
            account_security_service.credentials_integration, "is_password_change_required", return_value=True
        ),
        patch.object(
            account_security_service.server_settings_integration, "get_server_settings", return_value=settings
        ),
        patch.object(account_security_service, "stage_required_password_change", side_effect=_ReachedError),
    ):
        account_security_service.complete_password_change(
            "203.0.113.7", "agent", request, "web", store, MagicMock(), MagicMock(), db, device_id=None
        )


_FLOWS = [
    pytest.param(_reset, id="password-reset"),
    pytest.param(_verify_email, id="sign-up-confirmation"),
    pytest.param(_signup, id="sign-up"),
    pytest.param(_onboarding, id="onboarding"),
    pytest.param(_admin_create, id="admin-create"),
    pytest.param(_admin_set_password, id="admin-set-password"),
    pytest.param(_own_change, id="own-change"),
    pytest.param(_required_change, id="required-change"),
]


@pytest.mark.parametrize("flow", _FLOWS)
class TestBreachCheckInEveryFlow:
    def test_a_breached_password_is_refused_after_the_transaction_ends_and_before_the_flow_goes_on(self, flow):
        db = MagicMock()
        with _breach(True) as (check, settings), pytest.raises(credentials_contracts.PasswordBreachedError):
            flow(settings, db)

        check.assert_called_once_with(_PASSWORD)
        db.rollback.assert_called_once()
        db.commit.assert_not_called()

    def test_with_the_setting_off_nothing_is_sent_and_the_flow_goes_on(self, flow):
        db = MagicMock()
        with _breach(False) as (check, settings), pytest.raises(_ReachedError):
            flow(settings, db)

        check.assert_not_called()
        db.rollback.assert_not_called()
