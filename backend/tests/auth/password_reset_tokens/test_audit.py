"""Audit rows and the security-change event of a password reset."""

from unittest.mock import MagicMock, patch

import jasil.publisher as platform_publisher
import jasil.testing as jasil_testing
import pytest
from jasil.backends.state_memory import MemoryState

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


_REQUEST = password_reset_audit_actions.PASSWORD_RESET_REQUEST.id
_SERVICE = "modules.auth.password_reset_tokens.service"


class TestResetRequestAudit:
    @pytest.fixture(autouse=True)
    def _mail(self):
        with (
            patch(f"{_SERVICE}.server_settings_integration.is_mail_configured", return_value=True),
            patch(f"{_SERVICE}.password_reset_event_publishers.publish_password_reset_requested"),
        ):
            yield

    @staticmethod
    def _user(**fields):
        return patch(
            f"{_SERVICE}.users_integration.get_user_by_email",
            return_value=MagicMock(id=9, active=True, access_type="regular", **fields),
        )

    @staticmethod
    def _may_reset(allowed):
        return patch.object(password_reset_service, "_may_reset_password", return_value=allowed)

    def test_an_issued_reset_is_audited_against_the_user(self, mock_db):
        with self._user(), self._may_reset(True), jasil_testing.capture_audit() as audit:
            password_reset_service.request_password_reset_email("user@example.com", MemoryState(), mock_db)

        entry = audit.assert_audited(_REQUEST, target_type="user", target_id="9", target_owner_id="9")
        assert entry.details is None
        assert "user@example.com" not in repr(entry)
        mock_db.commit.assert_called_once()

    def test_an_unknown_address_is_recorded_without_a_target_or_the_address(self, mock_db):
        with (
            patch(f"{_SERVICE}.users_integration.get_user_by_email", return_value=None),
            jasil_testing.capture_audit() as audit,
        ):
            result = password_reset_service.request_password_reset_email("nobody@example.com", MemoryState(), mock_db)

        assert result is None
        entry = audit.assert_audited(_REQUEST, outcome="failure")
        assert entry.target_type is None
        assert "nobody@example.com" not in repr(entry)
        mock_db.commit.assert_not_called()

    def test_an_inactive_account_is_recorded_as_denied(self, mock_db):
        with (
            patch(
                f"{_SERVICE}.users_integration.get_user_by_email",
                return_value=MagicMock(id=9, active=False),
            ),
            jasil_testing.capture_audit() as audit,
        ):
            password_reset_service.request_password_reset_email("user@example.com", MemoryState(), mock_db)

        audit.assert_audited(_REQUEST, outcome="denied", target_type="user", target_id="9", target_owner_id="9")

    def test_an_account_without_a_local_password_is_recorded_as_denied(self, mock_db):
        with self._user(), self._may_reset(False), jasil_testing.capture_audit() as audit:
            password_reset_service.request_password_reset_email("user@example.com", MemoryState(), mock_db)

        audit.assert_audited(_REQUEST, outcome="denied", target_type="user", target_id="9", target_owner_id="9")

    def test_a_request_inside_the_cooldown_adds_no_row(self, mock_db):
        state = MemoryState()
        with self._user(), self._may_reset(True), jasil_testing.capture_audit() as audit:
            password_reset_service.request_password_reset_email("user@example.com", state, mock_db)
            password_reset_service.request_password_reset_email("user@example.com", state, mock_db)

        assert len([e for e in audit.entries if e.action_id == _REQUEST]) == 1

    def test_mail_not_configured_adds_no_row(self, mock_db):
        with (
            patch(f"{_SERVICE}.server_settings_integration.is_mail_configured", return_value=False),
            jasil_testing.capture_audit() as audit,
            pytest.raises(core_exceptions.ServiceUnavailableError),
        ):
            password_reset_service.request_password_reset_email("user@example.com", MemoryState(), mock_db)

        audit.assert_not_audited(_REQUEST)
