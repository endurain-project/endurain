"""Audit rows and ``auth.account_security_changed`` events written by the account-security workflows."""

from unittest.mock import MagicMock, patch

import jasil.publisher as platform_publisher
import jasil.testing as jasil_testing
import pytest

import core.exceptions as core_exceptions
import modules.auth.account_security.account_security_service as account_security_service
import modules.auth.account_security.api_key_service as api_key_service
import modules.auth.account_security.audit_actions as account_security_audit_actions
import modules.auth.account_security.event_publishers as account_security_event_publishers
import modules.auth.account_security.events as account_security_events
import modules.auth.account_security.identity_link_service as identity_link_service
import modules.auth.account_security.integration_service as account_security_integration
import modules.auth.account_security.mfa_workflow_service as mfa_workflow
import modules.auth.account_security.step_up_service as step_up_service
import modules.auth.api_keys.schema as api_keys_schema
import modules.auth.mfa.schema as mfa_schema
import modules.users.users.schema as users_schema

Change = account_security_events.AccountSecurityChange
Reason = account_security_audit_actions.StepUpFailureReason
Method = account_security_audit_actions.StepUpMethod


@pytest.fixture
def published():
    """Capture the events staged through ``publish_on_commit``."""
    with patch.object(platform_publisher, "publish_on_commit") as publish:
        yield publish


def assert_event(publish, change, user_id=7, idp_id=None):
    publish.assert_called_once()
    assert publish.call_args.args[0] == account_security_events.ACCOUNT_SECURITY_CHANGED
    assert publish.call_args.args[1] == {"user_id": user_id, "change": change.value, "idp_id": idp_id}


class TestPayloadAndPublisher:
    def test_payload_carries_ids_and_the_change_only(self):
        payload = account_security_events.AccountSecurityChangedPayload(
            user_id=7, change=Change.PASSWORD_CHANGED, extra="dropped"
        )

        assert payload.model_dump() == {"user_id": 7, "change": "password_changed", "idp_id": None}
        assert payload.SCHEMA_VERSION == 1

    def test_the_change_values(self):
        assert {c.value for c in Change} == {
            "password_changed",
            "password_reset",
            "password_set_by_admin",
            "mfa_enabled",
            "mfa_disabled",
            "backup_codes_generated",
            "api_key_created",
            "identity_provider_unlinked",
        }

    def test_the_event_is_staged_on_the_callers_session(self, mock_db, published):
        account_security_event_publishers.publish_account_security_changed(7, Change.MFA_ENABLED, mock_db)

        assert_event(published, Change.MFA_ENABLED)
        assert published.call_args.kwargs["db"] is mock_db
        assert published.call_args.kwargs["schema_version"] == 1


class TestPasswordAudit:
    def _stage_own(self, mock_db, *, revoke=True):
        with (
            patch.object(account_security_service.credentials_integration, "has_local_password", return_value=True),
            patch.object(account_security_service.step_up_service, "verify_step_up_credentials"),
            patch.object(account_security_service.server_settings_integration, "get_server_settings"),
            patch.object(account_security_service.users_integration, "require_user") as require_user,
            patch.object(account_security_service.credentials_integration, "validate_and_hash_password_for_user"),
            patch.object(account_security_service.credentials_integration, "set_local_password_hash"),
            patch.object(account_security_service.mfa_integration, "clear_pending_mfa_for_user"),
            patch.object(account_security_service.sessions_integration, "delete_sessions_by_user", return_value=3),
        ):
            require_user.return_value.access_type = "regular"
            account_security_service.stage_change_own_password(
                7,
                "old",
                "new",
                None,
                MagicMock(),
                mock_db,
                revoke_other_sessions=revoke,
                current_session_id="s",
            )

    def test_own_password_change(self, mock_db, published):
        with jasil_testing.capture_audit() as audit:
            self._stage_own(mock_db)

        entry = audit.assert_audited(
            account_security_audit_actions.PASSWORD_CHANGE.id, target_type="user", target_id="7", target_owner_id="7"
        )
        assert entry.details == {"sessions_revoked": 3}
        assert_event(published, Change.PASSWORD_CHANGED)

    def test_own_password_change_without_revoking_records_zero(self, mock_db, published):
        with jasil_testing.capture_audit() as audit:
            self._stage_own(mock_db, revoke=False)

        entry = audit.assert_audited(account_security_audit_actions.PASSWORD_CHANGE.id)
        assert entry.details == {"sessions_revoked": 0}

    def test_admin_sets_a_password(self, mock_db, published):
        with (
            patch.object(account_security_service.server_settings_integration, "get_server_settings"),
            patch.object(account_security_service.users_integration, "require_user") as require_user,
            patch.object(account_security_service.credentials_integration, "validate_and_hash_password_for_user"),
            patch.object(account_security_service.credentials_integration, "set_local_password_hash"),
            patch.object(account_security_service.sessions_integration, "delete_sessions_by_user", return_value=2),
            patch.object(account_security_service.mfa_integration, "clear_pending_mfa_for_user"),
            jasil_testing.capture_audit() as audit,
        ):
            require_user.return_value.access_type = "regular"
            account_security_service.change_managed_user_password(7, "new", mock_db)

        entry = audit.assert_audited(
            account_security_audit_actions.PASSWORD_SET.id, target_type="user", target_id="7", target_owner_id="7"
        )
        assert entry.details == {"sessions_revoked": 2}
        assert_event(published, Change.PASSWORD_SET_BY_ADMIN)


class TestMfaAudit:
    def test_enable(self, mock_db, published):
        store = MagicMock()
        store.get_secret.return_value = "secret"
        request = mfa_schema.MFASetupRequest(mfa_code="123456", current_password="pw")
        with (
            patch.object(mfa_workflow.step_up_service, "verify_step_up_credentials"),
            patch.object(mfa_workflow.mfa_integration, "enable_user_mfa", return_value=["a"]),
            jasil_testing.capture_audit() as audit,
        ):
            mfa_workflow.enable_mfa(request, 7, "sid", MagicMock(), store, mock_db)

        audit.assert_audited(
            account_security_audit_actions.MFA_ENABLE.id, target_type="user", target_id="7", target_owner_id="7"
        )
        assert_event(published, Change.MFA_ENABLED)

    def test_disable(self, mock_db, published):
        request = mfa_schema.MFADisableRequest(mfa_code="123456", current_password="pw")
        with (
            patch.object(mfa_workflow.step_up_service, "verify_step_up_credentials"),
            patch.object(mfa_workflow.mfa_integration, "disable_user_mfa"),
            jasil_testing.capture_audit() as audit,
        ):
            mfa_workflow.disable_mfa(request, 7, "sid", MagicMock(), mock_db)

        audit.assert_audited(
            account_security_audit_actions.MFA_DISABLE.id, target_type="user", target_id="7", target_owner_id="7"
        )
        assert_event(published, Change.MFA_DISABLED)

    def test_backup_codes(self, mock_db, published):
        step_up = users_schema.StepUpVerification(current_password="pw", mfa_code="123456")
        with (
            patch.object(mfa_workflow.users_integration, "get_user", return_value=MagicMock(id=7)),
            patch.object(mfa_workflow.mfa_integration, "is_mfa_enabled_for_user", return_value=True),
            patch.object(mfa_workflow.step_up_service, "verify_step_up_credentials"),
            patch.object(mfa_workflow.mfa_backup_codes_integration, "create_backup_codes", return_value=["a", "b"]),
            jasil_testing.capture_audit() as audit,
        ):
            mfa_workflow.generate_backup_codes(step_up, 7, "sid", MagicMock(), mock_db)

        entry = audit.assert_audited(
            account_security_audit_actions.BACKUP_CODES_GENERATE.id, target_type="user", target_id="7"
        )
        assert entry.details == {"count": 2}
        assert_event(published, Change.BACKUP_CODES_GENERATED)

    def test_a_refused_step_up_writes_nothing(self, mock_db, published):
        request = mfa_schema.MFADisableRequest(mfa_code="123456", current_password="pw")
        with (
            patch.object(
                mfa_workflow.step_up_service,
                "verify_step_up_credentials",
                side_effect=core_exceptions.UnauthenticatedError("no"),
            ),
            jasil_testing.capture_audit() as audit,
            pytest.raises(core_exceptions.UnauthenticatedError),
        ):
            mfa_workflow.disable_mfa(request, 7, "sid", MagicMock(), mock_db)

        audit.assert_not_audited(account_security_audit_actions.MFA_DISABLE.id)
        published.assert_not_called()


class TestApiKeyAudit:
    def test_create(self, mock_db, published):
        data = api_keys_schema.UsersApiKeyCreate(name="k", scopes=["activities:upload"], current_password="pw")
        created = MagicMock(id="key-1")
        created.model_dump.return_value = {
            "id": "key-1",
            "name": "k",
            "scopes": ["activities:upload"],
            "created_at": "2026-01-01T00:00:00Z",
            "expires_at": None,
            "last_used_at": None,
            "revoked_at": None,
            "key_prefix": "p",
        }
        with (
            patch.object(api_key_service.api_keys_integration, "validate_api_key_scopes"),
            patch.object(api_key_service.step_up_service, "verify_step_up_credentials"),
            patch.object(api_key_service.users_integration, "require_user"),
            patch.object(api_key_service.api_keys_integration, "generate_api_key", return_value="raw"),
            patch.object(api_key_service.api_keys_integration, "create_api_key", return_value=created),
            patch.object(api_keys_schema, "UsersApiKeyCreatedRead"),
            jasil_testing.capture_audit() as audit,
        ):
            api_key_service.create_user_api_key(7, "sid", data, MagicMock(), mock_db)

        entry = audit.assert_audited(
            account_security_audit_actions.API_KEY_CREATE.id,
            target_type="api_key",
            target_id="key-1",
            target_owner_id="7",
        )
        assert entry.details == {"scopes": ["activities:upload"]}
        assert_event(published, Change.API_KEY_CREATED)

    def test_revoke_and_delete(self, mock_db):
        with (
            patch.object(api_key_service.api_keys_integration, "revoke_api_key"),
            patch.object(api_key_service.api_keys_integration, "delete_api_key"),
            jasil_testing.capture_audit() as audit,
        ):
            api_key_service.revoke_user_api_key("key-1", 7, mock_db)
            api_key_service.delete_user_api_key("key-2", 7, mock_db)

        audit.assert_audited(
            account_security_audit_actions.API_KEY_REVOKE.id,
            target_type="api_key",
            target_id="key-1",
            target_owner_id="7",
        )
        audit.assert_audited(
            account_security_audit_actions.API_KEY_DELETE.id,
            target_type="api_key",
            target_id="key-2",
            target_owner_id="7",
        )


class TestSessionAudit:
    def test_one_session(self, mock_db):
        with (
            patch.object(account_security_service.sessions_integration, "delete_session"),
            jasil_testing.capture_audit() as audit,
        ):
            account_security_service.delete_user_session("sess-1", 7, mock_db)

        entry = audit.assert_audited(
            account_security_audit_actions.SESSION_REVOKE.id,
            target_type="session",
            target_id="sess-1",
            target_owner_id="7",
        )
        assert entry.details == {"sessions_revoked": 1}

    def test_other_sessions(self, mock_db):
        with (
            patch.object(account_security_service.sessions_integration, "delete_sessions_by_user", return_value=4),
            jasil_testing.capture_audit() as audit,
        ):
            account_security_service.delete_other_user_sessions(7, "sess-1", mock_db)

        entry = audit.assert_audited(
            account_security_audit_actions.SESSION_REVOKE.id, target_type="user", target_id="7", target_owner_id="7"
        )
        assert entry.details == {"sessions_revoked": 4}

    def test_all_sessions(self, mock_db):
        with (
            patch.object(account_security_service.sessions_integration, "delete_sessions_by_user", return_value=5),
            jasil_testing.capture_audit() as audit,
        ):
            account_security_service.delete_all_user_sessions(7, mock_db)

        entry = audit.assert_audited(
            account_security_audit_actions.SESSION_REVOKE.id, target_type="user", target_id="7", target_owner_id="7"
        )
        assert entry.details == {"sessions_revoked": 5}


class TestIdentityUnlinkAudit:
    def _patches(self):
        return (
            patch.object(identity_link_service.identity_providers_integration, "get_identity_provider"),
            patch.object(
                identity_link_service.identity_provider_links_integration,
                "get_user_identity_provider_by_user_id_and_idp_id",
            ),
            patch.object(
                identity_link_service.identity_provider_links_integration,
                "get_user_identity_providers_by_user_id",
                return_value=[1, 2],
            ),
            patch.object(identity_link_service.credentials_integration, "has_local_password", return_value=True),
            patch.object(
                identity_link_service.identity_provider_links_integration,
                "delete_user_identity_provider",
                return_value=True,
            ),
        )

    def test_own_unlink(self, mock_db, published):
        step_up = users_schema.StepUpVerification(current_password="pw")
        p = self._patches()
        with (
            p[0],
            p[1],
            p[2],
            p[3],
            p[4],
            patch.object(identity_link_service.step_up_service, "verify_step_up_credentials"),
            jasil_testing.capture_audit() as audit,
        ):
            identity_link_service.delete_identity_provider_link(3, step_up, 7, "sid", MagicMock(), mock_db)

        entry = audit.assert_audited(
            account_security_audit_actions.IDENTITY_LINK_UNLINK.id,
            target_type="user",
            target_id="7",
            target_owner_id="7",
        )
        assert entry.details == {"idp_id": 3}
        assert_event(published, Change.IDENTITY_PROVIDER_UNLINKED, idp_id=3)

    def test_admin_unlink(self, mock_db, published):
        p = self._patches()
        with p[0], p[1], p[2], p[3], p[4], jasil_testing.capture_audit() as audit:
            account_security_integration.admin_delete_identity_provider_link(7, 3, mock_db)

        entry = audit.assert_audited(
            account_security_audit_actions.IDENTITY_LINK_UNLINK.id, target_type="user", target_id="7"
        )
        assert entry.details == {"idp_id": 3}
        assert_event(published, Change.IDENTITY_PROVIDER_UNLINKED, idp_id=3)


class TestStepUpAudit:
    def _verify(self, store, *, password_valid=False, mfa=False, mfa_valid=True, password=None, mfa_code=None):
        with (
            patch.object(step_up_service.users_integration, "require_user"),
            patch.object(step_up_service.credentials_integration, "get_password_hash", return_value="hash"),
            patch.object(step_up_service.mfa_integration, "is_mfa_enabled_for_user", return_value=mfa),
            patch.object(step_up_service.mfa_integration, "verify_user_mfa", return_value=mfa_valid),
            patch.object(
                step_up_service.credentials_integration,
                "verify_and_update_password",
                return_value=(password_valid, None),
            ),
            patch.object(step_up_service.lockout_integration, "report_lockout_applied"),
        ):
            step_up_service.verify_step_up_credentials(7, password, mfa_code, store, MagicMock())

    def _store(self, *, locked=False):
        store = MagicMock()
        store.is_locked_out.return_value = locked
        store.get_lockout_time.return_value = None
        return store

    def test_a_wrong_password_is_a_failure(self):
        with jasil_testing.capture_audit() as audit, pytest.raises(core_exceptions.UnauthenticatedError):
            self._verify(self._store(), password="pw")

        entry = audit.assert_audited(
            account_security_audit_actions.STEP_UP_VERIFY.id,
            outcome="failure",
            target_type="user",
            target_id="7",
            target_owner_id="7",
        )
        assert entry.details == {"method": Method.PASSWORD.value, "reason": Reason.INVALID_CREDENTIALS.value}

    def test_a_wrong_mfa_code_is_a_failure(self):
        with jasil_testing.capture_audit() as audit, pytest.raises(core_exceptions.UnauthenticatedError):
            self._verify(
                self._store(), password="pw", password_valid=True, mfa=True, mfa_valid=False, mfa_code="000000"
            )

        entry = audit.assert_audited(account_security_audit_actions.STEP_UP_VERIFY.id, outcome="failure")
        assert entry.details == {"method": Method.MFA_CODE.value, "reason": Reason.INVALID_CREDENTIALS.value}

    def test_a_lockout_is_denied(self):
        with jasil_testing.capture_audit() as audit, pytest.raises(core_exceptions.TooManyRequestsError):
            self._verify(self._store(locked=True), password="pw")

        entry = audit.assert_audited(account_security_audit_actions.STEP_UP_VERIFY.id, outcome="denied")
        assert entry.details["reason"] == Reason.LOCKED_OUT.value

    def test_the_mfa_code_check_records_failure_and_lockout(self):
        with (
            patch.object(step_up_service.mfa_integration, "verify_user_mfa", return_value=False),
            patch.object(step_up_service.lockout_integration, "report_lockout_applied"),
            jasil_testing.capture_audit() as audit,
        ):
            assert step_up_service.verify_mfa_code(7, "000000", self._store(), MagicMock()) is False

        entry = audit.assert_audited(account_security_audit_actions.STEP_UP_VERIFY.id, outcome="failure")
        assert entry.details == {"method": Method.MFA_CODE.value, "reason": Reason.INVALID_CREDENTIALS.value}

    def test_success_writes_no_row(self):
        with jasil_testing.capture_audit() as audit:
            self._verify(self._store(), password="pw", password_valid=True)

        audit.assert_not_audited(account_security_audit_actions.STEP_UP_VERIFY.id)
