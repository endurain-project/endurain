"""A reset of an account whose email was never verified removes what a squatter may have attached."""

from contextlib import ExitStack
from unittest.mock import patch

import jasil.publisher as platform_publisher
import jasil.testing as jasil_testing
import pytest

import modules.auth.password_reset_tokens.audit_actions as password_reset_audit_actions
import modules.auth.password_reset_tokens.service as password_reset_service
from tests._helpers.auth import MOCK_USER_ID


def _reset(mock_db, *, email_verified: bool, mfa_enabled: bool):
    """Run a reset with its collaborators patched; return the patched cleanup collaborators and the audit capture."""
    mocks = {}
    with ExitStack() as stack:
        for target, name, kwargs in (
            (password_reset_service.password_reset_crud, "claim_password_reset_token", {"return_value": MOCK_USER_ID}),
            (password_reset_service.server_settings_integration, "get_server_settings", {}),
            (password_reset_service, "_may_reset_password", {"return_value": True}),
            (password_reset_service.credentials_integration, "ensure_password_differs_from_current", {}),
            (password_reset_service.credentials_integration, "validate_and_hash_password_for_user", {}),
            (password_reset_service.credentials_integration, "set_local_password_hash", {}),
            (password_reset_service.password_reset_crud, "mark_user_password_reset_tokens_used", {}),
            (password_reset_service.sessions_integration, "delete_sessions_by_user", {}),
            (password_reset_service.api_keys_integration, "revoke_user_api_keys", {}),
            (password_reset_service.authentication_integration, "clear_account_login_lockout", {}),
            (password_reset_service.lockout_integration, "clear_step_up_account_lockout", {}),
            (password_reset_service.mfa_integration, "clear_mfa_account_lockout", {}),
            (password_reset_service.mfa_integration, "is_mfa_enabled_for_user", {"return_value": mfa_enabled}),
            (password_reset_service.mfa_integration, "disable_user_mfa", {}),
            (password_reset_service.identity_links_integration, "delete_all_user_identity_providers", {}),
            (password_reset_service.users_integration, "stage_email_verification", {}),
            (platform_publisher, "publish_on_commit", {}),
        ):
            mocks[name] = stack.enter_context(patch.object(target, name, **kwargs))
        require_user = stack.enter_context(patch.object(password_reset_service.users_integration, "require_user"))
        require_user.return_value.access_type = "regular"
        require_user.return_value.username = "alice"
        require_user.return_value.email_verified = email_verified
        audit = stack.enter_context(jasil_testing.capture_audit())
        password_reset_service.use_password_reset_token("raw-token", "new-password", mock_db)
    return mocks, audit


def test_unverified_account_loses_links_and_factors_and_is_verified(mock_db):
    mocks, audit = _reset(mock_db, email_verified=False, mfa_enabled=True)

    mocks["delete_all_user_identity_providers"].assert_called_once_with(MOCK_USER_ID, mock_db)
    mocks["disable_user_mfa"].assert_called_once_with(MOCK_USER_ID, mock_db)
    mocks["stage_email_verification"].assert_called_once_with(
        MOCK_USER_ID, mocks["get_server_settings"].return_value, mock_db
    )
    entry = audit.assert_audited(password_reset_audit_actions.PASSWORD_RESET.id)
    assert entry.details["unverified_account_cleaned"] is True
    mock_db.commit.assert_called_once()


def test_unverified_account_without_a_factor_skips_the_mfa_removal(mock_db):
    mocks, audit = _reset(mock_db, email_verified=False, mfa_enabled=False)

    mocks["delete_all_user_identity_providers"].assert_called_once_with(MOCK_USER_ID, mock_db)
    mocks["disable_user_mfa"].assert_not_called()
    mocks["stage_email_verification"].assert_called_once()
    assert audit.assert_audited(password_reset_audit_actions.PASSWORD_RESET.id).details["unverified_account_cleaned"]


@pytest.mark.parametrize("mfa_enabled", [True, False])
def test_verified_account_keeps_links_and_factors(mock_db, mfa_enabled):
    mocks, audit = _reset(mock_db, email_verified=True, mfa_enabled=mfa_enabled)

    mocks["delete_all_user_identity_providers"].assert_not_called()
    mocks["disable_user_mfa"].assert_not_called()
    mocks["stage_email_verification"].assert_not_called()
    entry = audit.assert_audited(password_reset_audit_actions.PASSWORD_RESET.id)
    assert entry.details["unverified_account_cleaned"] is False
