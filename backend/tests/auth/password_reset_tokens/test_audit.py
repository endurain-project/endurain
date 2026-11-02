"""Audit rows and the security-change event of a password reset."""

from unittest.mock import patch

import jasil.publisher as platform_publisher
import jasil.testing as jasil_testing
import pytest

import core.exceptions as core_exceptions
import modules.auth.password_reset_tokens.audit_actions as password_reset_audit_actions
import modules.auth.password_reset_tokens.service as password_reset_service


def test_a_reset_is_audited_and_announced(mock_db):
    with (
        patch.object(password_reset_service.password_reset_crud, "claim_password_reset_token", return_value=7),
        patch.object(password_reset_service.server_settings_integration, "get_server_settings"),
        patch.object(password_reset_service.users_integration, "require_user") as require_user,
        patch.object(password_reset_service, "_may_reset_password", return_value=True),
        patch.object(password_reset_service.credentials_integration, "validate_and_hash_password_for_user"),
        patch.object(password_reset_service.credentials_integration, "set_local_password_hash"),
        patch.object(password_reset_service.password_reset_crud, "mark_user_password_reset_tokens_used"),
        patch.object(password_reset_service.sessions_integration, "delete_sessions_by_user"),
        patch.object(password_reset_service.mfa_integration, "clear_pending_mfa_for_user"),
        patch.object(platform_publisher, "publish_on_commit") as publish,
        jasil_testing.capture_audit() as audit,
    ):
        require_user.return_value.access_type = "regular"
        password_reset_service.use_password_reset_token("raw-token", "new-password", mock_db)

    audit.assert_audited(
        password_reset_audit_actions.PASSWORD_RESET.id, target_type="user", target_id="7", target_owner_id="7"
    )
    assert publish.call_args.args[1] == {"user_id": 7, "change": "password_reset", "idp_id": None}


def test_an_invalid_token_is_recorded_without_a_target(mock_db):
    with (
        patch.object(password_reset_service.password_reset_crud, "claim_password_reset_token", return_value=None),
        jasil_testing.capture_audit() as audit,
        pytest.raises(core_exceptions.InvalidInputError),
    ):
        password_reset_service.use_password_reset_token("raw-token", "new-password", mock_db)

    entry = audit.assert_audited(password_reset_audit_actions.PASSWORD_RESET.id, outcome="failure")
    assert entry.target_type is None
    assert "raw-token" not in repr(entry)
