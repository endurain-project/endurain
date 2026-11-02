"""Audit rows of confirming an emailed verification link."""

from unittest.mock import MagicMock, patch

import jasil.testing as jasil_testing
import pytest

import core.exceptions as core_exceptions
import modules.auth.sign_up_tokens.audit_actions as sign_up_audit_actions
import modules.auth.sign_up_tokens.service as sign_up_service

_MODULE = "modules.auth.sign_up_tokens.service"
_ACTION = sign_up_audit_actions.SIGN_UP_CONFIRM.id


def _settings(*, approval=False):
    return MagicMock(signup_require_email_verification=True, signup_require_admin_approval=approval)


def _claim(*, previous_email=None):
    return MagicMock(id="t1", user_id=7, email="u@example.com", previous_email=previous_email)


@pytest.fixture
def deps(request):
    names = ["credentials_integration", "sessions_integration", "mfa_integration", "users_integration"]
    mocks = {name: MagicMock() for name in names}
    with (
        patch(f"{_MODULE}.server_settings_integration.get_server_settings", return_value=_settings()),
        patch(f"{_MODULE}.server_settings_integration.is_mail_configured", return_value=False),
        patch(f"{_MODULE}.verify_sign_up_token", return_value=_claim()) as verify_token,
        patch.multiple(_MODULE, **mocks),
        patch(f"{_MODULE}.sign_up_event_publishers"),
    ):
        mocks["users_integration"].get_user.return_value = MagicMock(id=7, active=False, access_type="regular")
        mocks["users_integration"].is_deactivated.return_value = False
        mocks["credentials_integration"].validate_and_hash_password_for_user.return_value = "hashed"
        yield mocks | {"verify_token": verify_token}


def test_a_sign_up_confirmation_is_audited_with_the_password_flag(deps, mock_db):
    with jasil_testing.capture_audit() as audit:
        sign_up_service.verify_email("tok", "ChosenPass1!", mock_db)

    entry = audit.assert_audited(_ACTION, target_type="user", target_id="7", target_owner_id="7")
    assert entry.details == {"password_set": True}
    assert "ChosenPass1!" not in repr(entry)


def test_a_sign_up_pending_admin_approval_is_audited_once(deps, mock_db):
    with (
        patch(f"{_MODULE}.server_settings_integration.get_server_settings", return_value=_settings(approval=True)),
        jasil_testing.capture_audit() as audit,
    ):
        sign_up_service.verify_email("tok", "ChosenPass1!", mock_db)

    assert len([e for e in audit.entries if e.action_id == _ACTION]) == 1


def test_an_approval_sign_up_with_mail_is_audited_once(deps, mock_db):
    with (
        patch(f"{_MODULE}.server_settings_integration.get_server_settings", return_value=_settings(approval=True)),
        patch(f"{_MODULE}.server_settings_integration.is_mail_configured", return_value=True),
        patch(f"{_MODULE}.request_sign_up_admin_approval_emails"),
        patch(f"{_MODULE}.notifications_integration.create_admin_sign_up_approval_notifications", return_value=[]),
        jasil_testing.capture_audit() as audit,
    ):
        sign_up_service.verify_email("tok", "ChosenPass1!", mock_db)

    assert len([e for e in audit.entries if e.action_id == _ACTION]) == 1


def test_confirming_an_active_account_that_already_has_a_password_sets_none(deps, mock_db):
    deps["users_integration"].get_user.return_value = MagicMock(id=7, active=True, access_type="regular")
    deps["credentials_integration"].has_local_password.return_value = True

    with jasil_testing.capture_audit() as audit:
        sign_up_service.verify_email("tok", None, mock_db)

    entry = audit.assert_audited(_ACTION, target_type="user", target_id="7", target_owner_id="7")
    assert entry.details == {"password_set": False}


def test_an_email_change_confirmation_is_not_audited_here(deps, mock_db):
    deps["verify_token"].return_value = _claim(previous_email="old@example.com")
    deps["users_integration"].get_user.return_value = MagicMock(id=7, active=True, access_type="regular")

    with jasil_testing.capture_audit() as audit:
        sign_up_service.verify_email("tok", None, mock_db)

    audit.assert_not_audited(_ACTION)


def test_a_missing_password_is_not_audited(deps, mock_db):
    with jasil_testing.capture_audit() as audit, pytest.raises(core_exceptions.PasswordRequiredError):
        sign_up_service.verify_email("tok", None, mock_db)

    audit.assert_not_audited(_ACTION)


def test_an_invalid_token_is_recorded_as_a_failure_without_a_target(mock_db):
    with (
        patch(f"{_MODULE}.server_settings_integration.get_server_settings", return_value=_settings()),
        patch(f"{_MODULE}.sign_up_crud.claim_sign_up_token", return_value=None),
        jasil_testing.capture_audit() as audit,
        pytest.raises(core_exceptions.InvalidInputError),
    ):
        sign_up_service.verify_email("raw-token", None, mock_db)

    entry = audit.assert_audited(_ACTION, outcome="failure")
    assert entry.target_type is None
    assert entry.details == {"password_set": None}
    assert "raw-token" not in repr(entry)
