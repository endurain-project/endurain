"""Audit rows and ``auth.account_security_changed`` events written by the account-security workflows."""

import uuid
from datetime import UTC, datetime, timedelta
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
import modules.auth.login_audit.audit_actions as login_audit_actions
import modules.auth.mfa.schema as mfa_schema
import modules.auth.schema as auth_schema
import modules.auth.sessions.audit_actions as sessions_audit_actions

USER_ID = uuid.UUID(int=7)
IDP_ID = uuid.UUID(int=3)
Change = account_security_events.AccountSecurityChange
Reason = login_audit_actions.StepUpFailureReason
Method = login_audit_actions.StepUpMethod


@pytest.fixture
def published():
    """Capture the events staged through ``publish_on_commit``."""
    with patch.object(platform_publisher, "publish_on_commit") as publish:
        yield publish


def assert_event(publish, change, user_id=USER_ID, idp_id=None):
    publish.assert_called_once()
    assert publish.call_args.args[0] == account_security_events.ACCOUNT_SECURITY_CHANGED
    assert publish.call_args.args[1] == {
        "user_id": str(user_id),
        "change": change.value,
        "idp_id": None if idp_id is None else str(idp_id),
        "access_type": None,
    }


class TestPayloadAndPublisher:
    def test_payload_carries_ids_and_the_change_only(self):
        payload = account_security_events.AccountSecurityChangedPayload(
            user_id=USER_ID, change=Change.PASSWORD_CHANGED, extra="dropped"
        )

        assert payload.model_dump() == {
            "user_id": USER_ID,
            "change": "password_changed",
            "idp_id": None,
            "access_type": None,
        }
        assert payload.SCHEMA_VERSION == 1

    def test_the_change_values(self):
        assert {c.value for c in Change} == {
            "password_changed",
            "password_reset",
            "password_set_by_admin",
            "mfa_enabled",
            "mfa_disabled",
            "mfa_reset_by_admin",
            "password_change_required_by_admin",
            "backup_codes_generated",
            "api_key_created",
            "api_keys_revoked_by_admin",
            "identity_provider_unlinked",
            "account_locked",
            "mfa_locked",
            "backup_code_used",
            "refresh_token_reuse_detected",
            "role_changed_by_admin",
            "account_deactivated_by_admin",
            "account_deletion_requested",
            "username_changed",
            "step_up_session_ended",
            "step_up_locked",
        }

    def test_the_event_is_staged_on_the_callers_session(self, mock_db, published):
        account_security_event_publishers.publish_account_security_changed(USER_ID, Change.MFA_ENABLED, mock_db)

        assert_event(published, Change.MFA_ENABLED)
        assert published.call_args.kwargs["db"] is mock_db
        assert published.call_args.kwargs["schema_version"] == 1


class TestPasswordAudit:
    def _stage_own(self, mock_db, *, revoke=True):
        with (
            patch.object(account_security_service.credentials_integration, "has_local_password", return_value=True),
            patch.object(account_security_service.credentials_integration, "ensure_password_differs_from_current"),
            patch.object(account_security_service.step_up_service, "verify_step_up_credentials"),
            patch.object(account_security_service.server_settings_integration, "get_server_settings"),
            patch.object(account_security_service.users_integration, "require_user") as require_user,
            patch.object(account_security_service.credentials_integration, "validate_and_hash_password_for_user"),
            patch.object(account_security_service.credentials_integration, "set_local_password_hash"),
            patch.object(account_security_service.sessions_integration, "delete_sessions_by_user", return_value=3),
            patch.object(
                account_security_service.authentication_integration, "clear_account_login_lockout"
            ) as clear_lock,
        ):
            require_user.return_value.access_type = "regular"
            require_user.return_value.username = "alice"
            account_security_service.stage_change_own_password(
                USER_ID,
                "old",
                "new",
                None,
                MagicMock(),
                mock_db,
                revoke_other_sessions=revoke,
                current_session_id="s",
            )
        return clear_lock

    def test_own_password_change(self, mock_db, published):
        with jasil_testing.capture_audit() as audit:
            self._stage_own(mock_db)

        entry = audit.assert_audited(
            account_security_audit_actions.PASSWORD_CHANGE.id,
            target_type="user",
            target_id=str(USER_ID),
            target_owner_id=str(USER_ID),
        )
        assert entry.details == {"sessions_revoked": 3}
        assert_event(published, Change.PASSWORD_CHANGED)

    def test_own_password_change_lifts_the_account_sign_in_lock(self, mock_db, published):
        clear_lock = self._stage_own(mock_db)

        clear_lock.assert_called_once_with(USER_ID)

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
            patch.object(
                account_security_service.authentication_integration, "clear_account_login_lockout"
            ) as clear_lock,
            patch.object(
                account_security_service.lockout_integration, "clear_step_up_account_lockout"
            ) as clear_step_up,
            jasil_testing.capture_audit() as audit,
        ):
            require_user.return_value.access_type = "regular"
            require_user.return_value.username = "alice"
            account_security_service.change_managed_user_password(USER_ID, "new", mock_db)

        clear_lock.assert_called_once_with(USER_ID)
        clear_step_up.assert_called_once_with(USER_ID)

        entry = audit.assert_audited(
            account_security_audit_actions.PASSWORD_SET.id,
            target_type="user",
            target_id=str(USER_ID),
            target_owner_id=str(USER_ID),
        )
        assert entry.details == {"sessions_revoked": 2}
        assert_event(published, Change.PASSWORD_SET_BY_ADMIN)


class TestAdministratorCredentialAudit:
    @staticmethod
    def _sessions(revoked=2):
        return patch.object(
            account_security_service.sessions_integration, "delete_sessions_by_user", return_value=revoked
        )

    def test_admin_resets_mfa(self, mock_db, published):
        with (
            patch.object(account_security_service.mfa_integration, "disable_user_mfa") as disable,
            patch.object(account_security_service.users_integration, "require_user") as require_user,
            patch.object(account_security_service.mfa_integration, "clear_mfa_account_lockout") as clear_lock,
            self._sessions() as sessions,
            jasil_testing.capture_audit() as audit,
        ):
            require_user.return_value.username = "alice"
            account_security_service.reset_managed_user_mfa(USER_ID, mock_db)

        disable.assert_called_once_with(USER_ID, mock_db)
        clear_lock.assert_called_once_with(USER_ID)
        sessions.assert_called_once_with(USER_ID, mock_db)
        entry = audit.assert_audited(
            account_security_audit_actions.MFA_RESET.id,
            target_type="user",
            target_id=str(USER_ID),
            target_owner_id=str(USER_ID),
        )
        assert entry.details == {"sessions_revoked": 2}
        assert_event(published, Change.MFA_RESET_BY_ADMIN)

    def test_resetting_mfa_that_is_off_records_nothing(self, mock_db, published):
        with (
            patch.object(
                account_security_service.mfa_integration,
                "disable_user_mfa",
                side_effect=core_exceptions.ConflictError("MFA is not enabled for this user"),
            ),
            self._sessions() as sessions,
            jasil_testing.capture_audit() as audit,
            pytest.raises(core_exceptions.ConflictError),
        ):
            account_security_service.reset_managed_user_mfa(USER_ID, mock_db)

        sessions.assert_not_called()
        audit.assert_not_audited(account_security_audit_actions.MFA_RESET.id)
        published.assert_not_called()

    def test_admin_requires_a_password_change(self, mock_db, published):
        with (
            patch.object(account_security_service.users_integration, "require_user"),
            patch.object(account_security_service.credentials_integration, "require_password_change") as require,
            self._sessions() as sessions,
            jasil_testing.capture_audit() as audit,
        ):
            account_security_service.require_managed_user_password_change(USER_ID, mock_db)

        require.assert_called_once_with(USER_ID, mock_db)
        sessions.assert_called_once_with(USER_ID, mock_db)
        entry = audit.assert_audited(
            account_security_audit_actions.PASSWORD_CHANGE_REQUIRE.id,
            target_type="user",
            target_id=str(USER_ID),
            target_owner_id=str(USER_ID),
        )
        assert entry.details == {"sessions_revoked": 2}
        assert_event(published, Change.PASSWORD_CHANGE_REQUIRED_BY_ADMIN)

    def test_a_user_without_a_local_password_keeps_their_sessions(self, mock_db, published):
        with (
            patch.object(account_security_service.users_integration, "require_user"),
            patch.object(
                account_security_service.credentials_integration,
                "require_password_change",
                side_effect=core_exceptions.ConflictError(),
            ),
            self._sessions() as sessions,
            jasil_testing.capture_audit() as audit,
            pytest.raises(core_exceptions.ConflictError),
        ):
            account_security_service.require_managed_user_password_change(USER_ID, mock_db)

        sessions.assert_not_called()
        audit.assert_not_audited(account_security_audit_actions.PASSWORD_CHANGE_REQUIRE.id)
        published.assert_not_called()


class TestMfaAudit:
    @staticmethod
    def _revoker(revoked=3):
        return patch.object(
            account_security_service.sessions_integration, "delete_sessions_by_user", return_value=revoked
        )

    def _enable(self, mock_db, *, revoke=True, step_up_error=None):
        store = MagicMock()
        store.get_secret.return_value = "secret"
        request = mfa_schema.MFASetupRequest(
            totp_code="123456",
            step_up=auth_schema.StepUpVerification(current_password="pw"),
            revoke_other_sessions=revoke,
        )
        with (
            patch.object(mfa_workflow.step_up_service, "verify_step_up_credentials", side_effect=step_up_error),
            patch.object(mfa_workflow.mfa_integration, "enable_user_mfa", return_value=["a"]),
            patch.object(mfa_workflow.users_integration, "require_user") as require_user,
            patch.object(mfa_workflow.mfa_integration, "clear_mfa_account_lockout") as clear_lock,
            jasil_testing.capture_audit() as audit,
        ):
            require_user.return_value.username = "alice"
            mfa_workflow.enable_mfa(request, USER_ID, "sid", MagicMock(), store, mock_db)
        self.cleared = clear_lock
        return audit

    def _disable(self, mock_db, *, revoke=True):
        request = auth_schema.StepUpVerification(current_password="pw", mfa_code="123456")
        with (
            patch.object(mfa_workflow.step_up_service, "verify_step_up_credentials"),
            patch.object(mfa_workflow.mfa_integration, "disable_user_mfa"),
            patch.object(mfa_workflow.users_integration, "require_user") as require_user,
            patch.object(mfa_workflow.mfa_integration, "clear_mfa_account_lockout") as clear_lock,
            jasil_testing.capture_audit() as audit,
        ):
            require_user.return_value.username = "alice"
            mfa_workflow.disable_mfa(request, USER_ID, "sid", MagicMock(), mock_db, revoke_other_sessions=revoke)
        self.cleared = clear_lock
        return audit

    def _backup_codes(self, mock_db, *, revoke=True):
        step_up = auth_schema.StepUpVerification(current_password="pw", mfa_code="123456")
        with (
            patch.object(mfa_workflow.users_integration, "get_user", return_value=MagicMock(id=USER_ID)),
            patch.object(mfa_workflow.mfa_integration, "is_mfa_enabled_for_user", return_value=True),
            patch.object(mfa_workflow.step_up_service, "verify_step_up_credentials"),
            patch.object(mfa_workflow.mfa_backup_codes_integration, "create_backup_codes", return_value=["a", "b"]),
            jasil_testing.capture_audit() as audit,
        ):
            mfa_workflow.generate_backup_codes(
                step_up, USER_ID, "sid", MagicMock(), mock_db, revoke_other_sessions=revoke
            )
        return audit

    def test_enable(self, mock_db, published):
        with self._revoker(3) as delete:
            audit = self._enable(mock_db)

        delete.assert_called_once_with(USER_ID, mock_db, exclude_session_id="sid")
        entry = audit.assert_audited(
            account_security_audit_actions.MFA_ENABLE.id,
            target_type="user",
            target_id=str(USER_ID),
            target_owner_id=str(USER_ID),
        )
        assert entry.details == {"sessions_revoked": 3}
        assert_event(published, Change.MFA_ENABLED)
        self.cleared.assert_called_once_with(USER_ID)

    def test_enable_keeps_every_session_when_told_to(self, mock_db, published):
        with self._revoker(3) as delete:
            audit = self._enable(mock_db, revoke=False)

        delete.assert_not_called()
        assert audit.assert_audited(account_security_audit_actions.MFA_ENABLE.id).details == {"sessions_revoked": 0}

    def test_a_refused_step_up_on_enable_ends_nothing(self, mock_db, published):
        with self._revoker(3) as delete, pytest.raises(core_exceptions.UnauthenticatedError):
            self._enable(mock_db, step_up_error=core_exceptions.UnauthenticatedError("bad"))

        delete.assert_not_called()
        mock_db.commit.assert_not_called()

    def test_disable(self, mock_db, published):
        with self._revoker(2) as delete:
            audit = self._disable(mock_db)

        delete.assert_called_once_with(USER_ID, mock_db, exclude_session_id="sid")
        entry = audit.assert_audited(
            account_security_audit_actions.MFA_DISABLE.id,
            target_type="user",
            target_id=str(USER_ID),
            target_owner_id=str(USER_ID),
        )
        assert entry.details == {"sessions_revoked": 2}
        assert_event(published, Change.MFA_DISABLED)
        self.cleared.assert_called_once_with(USER_ID)

    def test_disable_keeps_every_session_when_told_to(self, mock_db, published):
        with self._revoker(2) as delete:
            audit = self._disable(mock_db, revoke=False)

        delete.assert_not_called()
        assert audit.assert_audited(account_security_audit_actions.MFA_DISABLE.id).details == {"sessions_revoked": 0}

    def test_a_refused_step_up_on_disable_ends_nothing(self, mock_db, published):
        request = auth_schema.StepUpVerification(current_password="pw", mfa_code="123456")
        with (
            self._revoker(2) as delete,
            patch.object(
                mfa_workflow.step_up_service,
                "verify_step_up_credentials",
                side_effect=core_exceptions.UnauthenticatedError("bad"),
            ),
            patch.object(mfa_workflow.mfa_integration, "disable_user_mfa"),
            pytest.raises(core_exceptions.UnauthenticatedError),
        ):
            mfa_workflow.disable_mfa(request, USER_ID, "sid", MagicMock(), mock_db, revoke_other_sessions=True)

        delete.assert_not_called()
        mock_db.commit.assert_not_called()

    def test_backup_codes(self, mock_db, published):
        with self._revoker(4) as delete:
            audit = self._backup_codes(mock_db)

        delete.assert_called_once_with(USER_ID, mock_db, exclude_session_id="sid")
        entry = audit.assert_audited(
            account_security_audit_actions.BACKUP_CODES_GENERATE.id, target_type="user", target_id=str(USER_ID)
        )
        assert entry.details == {"count": 2, "sessions_revoked": 4}
        assert_event(published, Change.BACKUP_CODES_GENERATED)

    def test_backup_codes_keep_every_session_when_told_to(self, mock_db, published):
        with self._revoker(4) as delete:
            audit = self._backup_codes(mock_db, revoke=False)

        delete.assert_not_called()
        entry = audit.assert_audited(account_security_audit_actions.BACKUP_CODES_GENERATE.id)
        assert entry.details == {"count": 2, "sessions_revoked": 0}

    def test_a_refused_step_up_on_backup_codes_ends_nothing(self, mock_db, published):
        step_up = auth_schema.StepUpVerification(current_password="pw", mfa_code="123456")
        with (
            self._revoker(4) as delete,
            patch.object(mfa_workflow.users_integration, "get_user", return_value=MagicMock(id=USER_ID)),
            patch.object(mfa_workflow.mfa_integration, "is_mfa_enabled_for_user", return_value=True),
            patch.object(
                mfa_workflow.step_up_service,
                "verify_step_up_credentials",
                side_effect=core_exceptions.UnauthenticatedError("bad"),
            ),
            pytest.raises(core_exceptions.UnauthenticatedError),
        ):
            mfa_workflow.generate_backup_codes(
                step_up, USER_ID, "sid", MagicMock(), mock_db, revoke_other_sessions=True
            )

        delete.assert_not_called()
        mock_db.commit.assert_not_called()


class TestApiKeyAudit:
    def test_create(self, mock_db, published):
        data = api_keys_schema.UserApiKeyCreate(
            name="k", scopes=["activities:upload"], step_up={"current_password": "pw"}
        )
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
            patch.object(api_key_service.step_up_service, "verify_step_up_credentials"),
            patch.object(api_key_service.users_integration, "require_user"),
            patch.object(api_key_service.api_keys_integration, "count_active_api_keys", return_value=0),
            patch.object(api_key_service.api_keys_integration, "generate_api_key", return_value="raw"),
            patch.object(api_key_service.api_keys_integration, "create_api_key", return_value=created),
            patch.object(api_keys_schema, "UserApiKeyCreatedRead"),
            jasil_testing.capture_audit() as audit,
        ):
            api_key_service.create_user_api_key(USER_ID, "sid", data, datetime.now(UTC), MagicMock(), mock_db)

        entry = audit.assert_audited(
            account_security_audit_actions.API_KEY_CREATE.id,
            target_type="api_key",
            target_id="key-1",
            target_owner_id=str(USER_ID),
        )
        assert entry.details == {"scopes": ["activities:upload"]}
        assert_event(published, Change.API_KEY_CREATED)

    def test_revoke_and_delete(self, mock_db):
        with (
            patch.object(api_key_service.api_keys_integration, "revoke_api_key"),
            patch.object(api_key_service.api_keys_integration, "delete_api_key"),
            jasil_testing.capture_audit() as audit,
        ):
            api_key_service.revoke_user_api_key("key-1", USER_ID, mock_db)
            api_key_service.delete_user_api_key("key-2", USER_ID, mock_db)

        audit.assert_audited(
            account_security_audit_actions.API_KEY_REVOKE.id,
            target_type="api_key",
            target_id="key-1",
            target_owner_id=str(USER_ID),
        )
        audit.assert_audited(
            account_security_audit_actions.API_KEY_DELETE.id,
            target_type="api_key",
            target_id="key-2",
            target_owner_id=str(USER_ID),
        )


class TestSessionAudit:
    def test_one_session(self, mock_db):
        with (
            patch.object(account_security_service.sessions_integration, "delete_session"),
            jasil_testing.capture_audit() as audit,
        ):
            account_security_service.delete_user_session("sess-1", USER_ID, mock_db)

        entry = audit.assert_audited(
            sessions_audit_actions.SESSION_REVOKE.id,
            target_type="session",
            target_id="sess-1",
            target_owner_id=str(USER_ID),
        )
        assert entry.details == {"sessions_revoked": 1}

    def test_other_sessions(self, mock_db):
        with (
            patch.object(account_security_service.sessions_integration, "delete_sessions_by_user", return_value=4),
            jasil_testing.capture_audit() as audit,
        ):
            account_security_service.delete_other_user_sessions(USER_ID, "sess-1", mock_db)

        entry = audit.assert_audited(
            sessions_audit_actions.SESSION_REVOKE.id,
            target_type="user",
            target_id=str(USER_ID),
            target_owner_id=str(USER_ID),
        )
        assert entry.details == {"sessions_revoked": 4}

    def test_all_sessions(self, mock_db):
        with (
            patch.object(account_security_service.sessions_integration, "delete_sessions_by_user", return_value=5),
            jasil_testing.capture_audit() as audit,
        ):
            account_security_service.delete_all_user_sessions(USER_ID, mock_db)

        entry = audit.assert_audited(
            sessions_audit_actions.SESSION_REVOKE.id,
            target_type="user",
            target_id=str(USER_ID),
            target_owner_id=str(USER_ID),
        )
        assert entry.details == {"sessions_revoked": 5}

    def test_sign_out_everywhere(self, mock_db):
        with (
            patch.object(
                account_security_service.sessions_integration, "delete_sessions_by_user", return_value=3
            ) as end,
            jasil_testing.capture_audit() as audit,
        ):
            revoked = account_security_service.sign_out_everywhere(USER_ID, mock_db)

        assert revoked == 3
        end.assert_called_once_with(USER_ID, mock_db)
        entry = audit.assert_audited(
            sessions_audit_actions.SESSION_REVOKE.id,
            target_type="user",
            target_id=str(USER_ID),
            target_owner_id=str(USER_ID),
        )
        assert entry.details == {"sessions_revoked": 3}
        mock_db.commit.assert_called_once()


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
        step_up = auth_schema.StepUpVerification(current_password="pw")
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
            identity_link_service.delete_identity_provider_link(IDP_ID, step_up, USER_ID, "sid", MagicMock(), mock_db)

        entry = audit.assert_audited(
            account_security_audit_actions.IDENTITY_LINK_UNLINK.id,
            target_type="user",
            target_id=str(USER_ID),
            target_owner_id=str(USER_ID),
        )
        assert entry.details == {"idp_id": str(IDP_ID)}
        assert_event(published, Change.IDENTITY_PROVIDER_UNLINKED, idp_id=IDP_ID)

    @pytest.mark.parametrize("admin", [False, True])
    def test_an_unlink_audits_the_sessions_it_ends(self, mock_db, published, admin):
        p = self._patches()
        with (
            p[0],
            p[1],
            p[2],
            p[3],
            p[4],
            patch.object(identity_link_service.step_up_service, "verify_step_up_credentials"),
            patch.object(
                identity_link_service.identity_provider_links_integration, "end_idp_sessions", return_value=2
            ) as end_sessions,
            jasil_testing.capture_audit() as audit,
        ):
            if admin:
                account_security_integration.admin_delete_identity_provider_link(USER_ID, IDP_ID, mock_db)
            else:
                step_up = auth_schema.StepUpVerification(current_password="pw")
                identity_link_service.delete_identity_provider_link(
                    IDP_ID, step_up, USER_ID, "sid", MagicMock(), mock_db
                )

        end_sessions.assert_called_once_with(USER_ID, IDP_ID, mock_db)
        entry = audit.assert_audited(
            sessions_audit_actions.SESSION_REVOKE.id,
            target_type="user",
            target_id=str(USER_ID),
            target_owner_id=str(USER_ID),
        )
        assert entry.details == {"sessions_revoked": 2}
        audit.assert_audited(account_security_audit_actions.IDENTITY_LINK_UNLINK.id)

    def test_an_unlink_that_ends_no_session_audits_no_revocation(self, mock_db, published):
        p = self._patches()
        with (
            p[0],
            p[1],
            p[2],
            p[3],
            p[4],
            patch.object(identity_link_service.identity_provider_links_integration, "end_idp_sessions", return_value=0),
            jasil_testing.capture_audit() as audit,
        ):
            account_security_integration.admin_delete_identity_provider_link(USER_ID, IDP_ID, mock_db)

        audit.assert_not_audited(sessions_audit_actions.SESSION_REVOKE.id)

    def test_admin_unlink(self, mock_db, published):
        p = self._patches()
        with p[0], p[1], p[2], p[3], p[4], jasil_testing.capture_audit() as audit:
            account_security_integration.admin_delete_identity_provider_link(USER_ID, IDP_ID, mock_db)

        entry = audit.assert_audited(
            account_security_audit_actions.IDENTITY_LINK_UNLINK.id, target_type="user", target_id=str(USER_ID)
        )
        assert entry.details == {"idp_id": str(IDP_ID)}
        assert_event(published, Change.IDENTITY_PROVIDER_UNLINKED, idp_id=IDP_ID)


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
            step_up_service.verify_step_up_credentials(
                USER_ID, password, mfa_code, store, MagicMock(), session_id="sid-7"
            )

    def _store(self, *, locked=False):
        store = MagicMock()
        store.get_lockout_time.return_value = datetime.now(UTC) + timedelta(minutes=5) if locked else None
        store.get_account_lockout_time.return_value = None
        store.record_failed_attempt.return_value = 1
        store.record_account_failure.return_value = False
        return store

    def test_a_wrong_password_is_a_failure(self):
        with jasil_testing.capture_audit() as audit, pytest.raises(core_exceptions.StepUpFailedError):
            self._verify(self._store(), password="pw")

        entry = audit.assert_audited(
            login_audit_actions.STEP_UP_VERIFY.id,
            outcome="failure",
            target_type="user",
            target_id=str(USER_ID),
            target_owner_id=str(USER_ID),
        )
        assert entry.details == {"method": Method.PASSWORD.value, "reason": Reason.INVALID_CREDENTIALS.value}

    def test_a_wrong_mfa_code_is_a_failure(self):
        with jasil_testing.capture_audit() as audit, pytest.raises(core_exceptions.StepUpFailedError):
            self._verify(
                self._store(), password="pw", password_valid=True, mfa=True, mfa_valid=False, mfa_code="000000"
            )

        entry = audit.assert_audited(login_audit_actions.STEP_UP_VERIFY.id, outcome="failure")
        assert entry.details == {"method": Method.MFA_CODE.value, "reason": Reason.INVALID_CREDENTIALS.value}

    def test_a_lockout_is_denied(self):
        with jasil_testing.capture_audit() as audit, pytest.raises(core_exceptions.TooManyRequestsError):
            self._verify(self._store(locked=True), password="pw")

        entry = audit.assert_audited(login_audit_actions.STEP_UP_VERIFY.id, outcome="denied")
        assert entry.details["reason"] == Reason.LOCKED_OUT.value

    def test_success_writes_no_row(self):
        with jasil_testing.capture_audit() as audit:
            self._verify(self._store(), password="pw", password_valid=True)

        audit.assert_not_audited(login_audit_actions.STEP_UP_VERIFY.id)
