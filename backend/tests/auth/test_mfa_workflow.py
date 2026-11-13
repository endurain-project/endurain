"""Tests for the account-security MFA workflow.

mfa_workflow is the security-critical route-facing facade profile routes call.
It owns step-up verification, the pending setup-secret store, and response
shaping while orchestrating the lower-level ``modules.auth.mfa.service`` /
``modules.auth.mfa_backup_codes.crud`` helpers.

These tests mock the lower-level helpers (patched at the
``modules.auth.account_security.mfa_workflow_service`` namespace) and assert the orchestration
behaviour: delegation arguments, step-up enforcement, the pending-secret
store lifecycle, error propagation, and response/schema shaping.
"""

import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock, patch

import pytest
from fastapi import status

import core.exceptions as core_exceptions
import modules.auth.account_security.mfa_workflow_service as mfa_workflow
import modules.auth.credentials.integration_service as credentials_integration
import modules.auth.identity_providers.constants as identity_providers_constants
import modules.auth.mfa.schema as mfa_schema
import modules.auth.mfa_backup_codes.schema as mfa_backup_codes_schema
import modules.auth.schema as auth_schema
from tests._helpers.auth import MOCK_USER_ID

_SID = uuid.UUID("00000000-0000-4000-8000-0000000000a1")


@pytest.fixture
def step_up_store() -> MagicMock:
    """Return a mock StepUpStore."""
    return MagicMock()


@pytest.fixture
def mfa_secret_store() -> MagicMock:
    """Return a mock pending-secret store backend."""
    return MagicMock()


# ---------------------------------------------------------------------------
# get_mfa_status
# ---------------------------------------------------------------------------


class TestGetMfaStatus:
    """get_mfa_status reports enablement via mfa_service."""

    def test_returns_enabled_true(self, mock_db):
        with patch(
            "modules.auth.account_security.mfa_workflow_service.mfa_integration.is_mfa_enabled_for_user",
            return_value=True,
        ) as mock_is_enabled:
            result = mfa_workflow.get_mfa_status(MOCK_USER_ID, mock_db)

        mock_is_enabled.assert_called_once_with(MOCK_USER_ID, mock_db)
        assert isinstance(result, mfa_schema.MFAStatusRead)
        assert result.mfa_enabled is True

    def test_returns_enabled_false(self, mock_db):
        with patch(
            "modules.auth.account_security.mfa_workflow_service.mfa_integration.is_mfa_enabled_for_user",
            return_value=False,
        ):
            result = mfa_workflow.get_mfa_status(MOCK_USER_ID, mock_db)

        assert result.mfa_enabled is False


# ---------------------------------------------------------------------------
# get_backup_code_status
# ---------------------------------------------------------------------------


class TestGetBackupCodeStatus:
    """get_backup_code_status aggregates stored backup codes."""

    def test_no_codes_returns_empty_status(self, mock_db):
        with patch(
            "modules.auth.account_security.mfa_workflow_service.mfa_backup_codes_integration.get_user_backup_codes",
            return_value=[],
        ) as mock_get:
            result = mfa_workflow.get_backup_code_status(MOCK_USER_ID, mock_db)

        mock_get.assert_called_once_with(MOCK_USER_ID, mock_db)
        assert result.has_codes is False
        assert result.total == 0
        assert result.unused == 0
        assert result.used == 0
        assert result.created_at is None

    def test_counts_used_and_unused(self, mock_db):
        created = datetime(2026, 1, 1, 12, 0, 0)
        codes = [
            MagicMock(used=False, created_at=created),
            MagicMock(used=False, created_at=created),
            MagicMock(used=True, created_at=created),
        ]
        with patch(
            "modules.auth.account_security.mfa_workflow_service.mfa_backup_codes_integration.get_user_backup_codes",
            return_value=codes,
        ):
            result = mfa_workflow.get_backup_code_status(MOCK_USER_ID, mock_db)

        assert result.has_codes is True
        assert result.total == 3
        assert result.unused == 2
        assert result.used == 1
        assert result.created_at == created


# ---------------------------------------------------------------------------
# setup_mfa
# ---------------------------------------------------------------------------


class TestSetupMfa:
    """setup_mfa stores the pending secret returned by mfa_service."""

    def test_stores_pending_secret_and_returns_response(self, mock_db, mfa_secret_store):
        response = MagicMock()
        response.secret = "TOTPSECRET"
        with patch(
            "modules.auth.account_security.mfa_workflow_service.mfa_integration.setup_user_mfa",
            return_value=response,
        ) as mock_setup:
            result = mfa_workflow.setup_mfa(MOCK_USER_ID, mfa_secret_store, mock_db)

        mock_setup.assert_called_once_with(MOCK_USER_ID, mock_db)
        mfa_secret_store.add_secret.assert_called_once_with(MOCK_USER_ID, "TOTPSECRET")
        assert result is response


# ---------------------------------------------------------------------------
# enable_mfa
# ---------------------------------------------------------------------------


class TestEnableMfa:
    """enable_mfa enforces step-up, consumes pending secret, owns cleanup."""

    def _request(self) -> mfa_schema.MFASetupRequest:
        return mfa_schema.MFASetupRequest(
            totp_code="123456", step_up=auth_schema.StepUpVerification(current_password="old-pass")
        )

    def test_happy_path_enables_and_clears_pending_secret(self, mock_db, step_up_store, mfa_secret_store):
        mfa_secret_store.get_secret.return_value = "pending-secret"
        with (
            patch(
                "modules.auth.account_security.mfa_workflow_service.step_up_service.verify_step_up_credentials"
            ) as mock_verify,
            patch(
                "modules.auth.account_security.mfa_workflow_service.mfa_integration.enable_user_mfa",
                return_value=["code-1", "code-2"],
            ) as mock_enable,
            patch("modules.auth.account_security.mfa_workflow_service.users_integration.require_user"),
            patch("modules.auth.account_security.mfa_workflow_service.mfa_integration.clear_mfa_account_lockout"),
            patch("modules.auth.account_security.mfa_workflow_service.logger") as mock_log,
        ):
            result = mfa_workflow.enable_mfa(
                self._request(),
                MOCK_USER_ID,
                _SID,
                step_up_store,
                mfa_secret_store,
                mock_db,
            )

        mock_verify.assert_called_once_with(
            MOCK_USER_ID,
            "old-pass",
            None,
            step_up_store,
            mock_db,
            idp_reauth=None,
            session_id=_SID,
            action=identity_providers_constants.StepUpAction.MFA_ENABLE,
        )
        mock_enable.assert_called_once_with(
            MOCK_USER_ID,
            "pending-secret",
            "123456",
            credentials_integration.get_password_hasher(),
            mock_db,
            replay_guard=step_up_store,
        )
        mfa_secret_store.delete_secret.assert_called_once_with(MOCK_USER_ID)
        assert len(mock_log.method_calls) == 1
        assert isinstance(result, mfa_backup_codes_schema.MFABackupCodesRead)
        assert set(result.model_dump()) == {"codes", "created_at"}
        assert result.codes == ["code-1", "code-2"]
        assert abs(datetime.now(UTC) - result.created_at) < timedelta(seconds=5)

    def test_step_up_failure_propagates_before_enabling(self, mock_db, step_up_store, mfa_secret_store):
        mfa_secret_store.get_secret.return_value = "pending-secret"
        with (
            patch(
                "modules.auth.account_security.mfa_workflow_service.step_up_service.verify_step_up_credentials",
                side_effect=core_exceptions.UnauthenticatedError("bad password"),
            ),
            patch("modules.auth.account_security.mfa_workflow_service.mfa_integration.enable_user_mfa") as mock_enable,
            pytest.raises(core_exceptions.DomainError) as exc_info,
        ):
            mfa_workflow.enable_mfa(
                self._request(),
                MOCK_USER_ID,
                _SID,
                step_up_store,
                mfa_secret_store,
                mock_db,
            )

        assert exc_info.value.status_code == 401
        mock_enable.assert_not_called()
        mfa_secret_store.delete_secret.assert_not_called()

    def test_no_pending_secret_raises_409(self, mock_db, step_up_store, mfa_secret_store):
        mfa_secret_store.get_secret.return_value = None
        with (
            patch(
                "modules.auth.account_security.mfa_workflow_service.step_up_service.verify_step_up_credentials"
            ) as mock_verify,
            patch("modules.auth.account_security.mfa_workflow_service.mfa_integration.enable_user_mfa") as mock_enable,
            pytest.raises(core_exceptions.DomainError) as exc_info,
        ):
            mfa_workflow.enable_mfa(
                self._request(),
                MOCK_USER_ID,
                _SID,
                step_up_store,
                mfa_secret_store,
                mock_db,
            )

        assert isinstance(exc_info.value, core_exceptions.ConflictError)
        assert exc_info.value.status_code == status.HTTP_409_CONFLICT
        mock_verify.assert_not_called()
        mock_enable.assert_not_called()
        mfa_secret_store.delete_secret.assert_not_called()

    def test_invalid_mfa_code_keeps_pending_secret_for_retry(self, mock_db, step_up_store, mfa_secret_store):
        """A wrong TOTP code must NOT discard the pending secret (allow retry)."""
        mfa_secret_store.get_secret.return_value = "pending-secret"
        with (
            patch("modules.auth.account_security.mfa_workflow_service.step_up_service.verify_step_up_credentials"),
            patch(
                "modules.auth.account_security.mfa_workflow_service.mfa_integration.enable_user_mfa",
                side_effect=core_exceptions.InvalidMfaCodeError(),
            ),
            pytest.raises(core_exceptions.DomainError) as exc_info,
        ):
            mfa_workflow.enable_mfa(
                self._request(),
                MOCK_USER_ID,
                _SID,
                step_up_store,
                mfa_secret_store,
                mock_db,
            )

        assert exc_info.value.detail == "Invalid MFA code"
        mfa_secret_store.delete_secret.assert_not_called()

    def test_other_enable_error_discards_pending_secret(self, mock_db, step_up_store, mfa_secret_store):
        """Any non-"Invalid MFA code" failure clears the pending secret."""
        mfa_secret_store.get_secret.return_value = "pending-secret"
        with (
            patch("modules.auth.account_security.mfa_workflow_service.step_up_service.verify_step_up_credentials"),
            patch(
                "modules.auth.account_security.mfa_workflow_service.mfa_integration.enable_user_mfa",
                side_effect=core_exceptions.ConflictError("MFA already enabled"),
            ),
            pytest.raises(core_exceptions.DomainError) as exc_info,
        ):
            mfa_workflow.enable_mfa(
                self._request(),
                MOCK_USER_ID,
                _SID,
                step_up_store,
                mfa_secret_store,
                mock_db,
            )

        assert exc_info.value.status_code == status.HTTP_409_CONFLICT
        mfa_secret_store.delete_secret.assert_called_once_with(MOCK_USER_ID)

    def test_same_detail_without_the_mfa_code_type_discards_secret(self, mock_db, step_up_store, mfa_secret_store):
        """Only the dedicated wrong-code type keeps the pending secret, not a matching message."""
        mfa_secret_store.get_secret.return_value = "pending-secret"
        with (
            patch("modules.auth.account_security.mfa_workflow_service.step_up_service.verify_step_up_credentials"),
            patch(
                "modules.auth.account_security.mfa_workflow_service.mfa_integration.enable_user_mfa",
                side_effect=core_exceptions.InvalidInputError("Invalid MFA code"),
            ),
            pytest.raises(core_exceptions.DomainError),
        ):
            mfa_workflow.enable_mfa(
                self._request(),
                MOCK_USER_ID,
                _SID,
                step_up_store,
                mfa_secret_store,
                mock_db,
            )

        mfa_secret_store.delete_secret.assert_called_once_with(MOCK_USER_ID)


# ---------------------------------------------------------------------------
# disable_mfa
# ---------------------------------------------------------------------------


class TestDisableMfa:
    """disable_mfa requires step-up (password + MFA code)."""

    def _request(self) -> auth_schema.StepUpVerification:
        return auth_schema.StepUpVerification(mfa_code="123456", current_password="old-pass")

    def test_happy_path_disables_after_step_up(self, mock_db, step_up_store):
        with (
            patch(
                "modules.auth.account_security.mfa_workflow_service.step_up_service.verify_step_up_credentials"
            ) as mock_verify,
            patch(
                "modules.auth.account_security.mfa_workflow_service.mfa_integration.disable_user_mfa"
            ) as mock_disable,
            patch("modules.auth.account_security.mfa_workflow_service.users_integration.require_user"),
            patch("modules.auth.account_security.mfa_workflow_service.mfa_integration.clear_mfa_account_lockout"),
            patch("modules.auth.account_security.mfa_workflow_service.logger") as mock_log,
        ):
            result = mfa_workflow.disable_mfa(
                self._request(),
                MOCK_USER_ID,
                _SID,
                step_up_store,
                mock_db,
                revoke_other_sessions=False,
            )

        mock_verify.assert_called_once_with(
            MOCK_USER_ID,
            "old-pass",
            "123456",
            step_up_store,
            mock_db,
            idp_reauth=None,
            session_id=_SID,
            action=identity_providers_constants.StepUpAction.MFA_DISABLE,
        )
        mock_disable.assert_called_once_with(MOCK_USER_ID, mock_db)
        assert len(mock_log.method_calls) == 1
        assert result is None

    def test_step_up_failure_does_not_disable(self, mock_db, step_up_store):
        with (
            patch(
                "modules.auth.account_security.mfa_workflow_service.step_up_service.verify_step_up_credentials",
                side_effect=core_exceptions.UnauthenticatedError("bad"),
            ),
            patch(
                "modules.auth.account_security.mfa_workflow_service.mfa_integration.disable_user_mfa"
            ) as mock_disable,
            pytest.raises(core_exceptions.DomainError) as exc_info,
        ):
            mfa_workflow.disable_mfa(
                self._request(),
                MOCK_USER_ID,
                _SID,
                step_up_store,
                mock_db,
                revoke_other_sessions=False,
            )

        assert exc_info.value.status_code == 401
        mock_disable.assert_not_called()


# ---------------------------------------------------------------------------
# generate_backup_codes
# ---------------------------------------------------------------------------


class TestGenerateBackupCodes:
    """generate_backup_codes gates on user existence, MFA state, and step-up."""

    def _step_up(self) -> auth_schema.StepUpVerification:
        return auth_schema.StepUpVerification(current_password="old-pass", mfa_code="123456")

    def test_happy_path_returns_codes(self, mock_db, step_up_store):
        user = MagicMock()
        user.id = MOCK_USER_ID
        with (
            patch("modules.auth.account_security.mfa_workflow_service.users_integration.get_user", return_value=user),
            patch(
                "modules.auth.account_security.mfa_workflow_service.mfa_integration.is_mfa_enabled_for_user",
                return_value=True,
            ),
            patch(
                "modules.auth.account_security.mfa_workflow_service.step_up_service.verify_step_up_credentials"
            ) as mock_verify,
            patch(
                "modules.auth.account_security.mfa_workflow_service.mfa_backup_codes_integration.create_backup_codes",
                return_value=["a", "b", "c"],
            ) as mock_create,
            patch("modules.auth.account_security.mfa_workflow_service.logger"),
        ):
            result = mfa_workflow.generate_backup_codes(
                self._step_up(),
                MOCK_USER_ID,
                _SID,
                step_up_store,
                mock_db,
                revoke_other_sessions=False,
            )

        mock_verify.assert_called_once_with(
            MOCK_USER_ID,
            "old-pass",
            "123456",
            step_up_store,
            mock_db,
            idp_reauth=None,
            session_id=_SID,
            action=identity_providers_constants.StepUpAction.MFA_BACKUP_CODES,
        )
        mock_create.assert_called_once_with(MOCK_USER_ID, credentials_integration.get_password_hasher(), mock_db)
        assert result.codes == ["a", "b", "c"]
        assert result.created_at is not None

    def test_regenerating_backup_codes_does_not_bump_the_security_generation(self, mock_db, step_up_store):
        prefix = "modules.auth.account_security.mfa_workflow_service."
        with (
            patch(prefix + "users_integration.get_user", return_value=MagicMock(id=MOCK_USER_ID)),
            patch(prefix + "mfa_integration.is_mfa_enabled_for_user", return_value=True),
            patch(prefix + "step_up_service.verify_step_up_credentials"),
            patch(prefix + "mfa_backup_codes_integration.create_backup_codes", return_value=["a"]),
            patch(prefix + "logger"),
            patch("modules.auth.security_generation.crud.bump") as bump,
        ):
            mfa_workflow.generate_backup_codes(
                self._step_up(), MOCK_USER_ID, _SID, step_up_store, mock_db, revoke_other_sessions=False
            )

        bump.assert_not_called()

    def test_user_not_found_raises_404(self, mock_db, step_up_store):
        with (
            patch("modules.auth.account_security.mfa_workflow_service.users_integration.get_user", return_value=None),
            patch(
                "modules.auth.account_security.mfa_workflow_service.step_up_service.verify_step_up_credentials"
            ) as mock_verify,
            pytest.raises(core_exceptions.DomainError) as exc_info,
        ):
            mfa_workflow.generate_backup_codes(
                self._step_up(),
                MOCK_USER_ID,
                _SID,
                step_up_store,
                mock_db,
                revoke_other_sessions=False,
            )

        assert exc_info.value.status_code == status.HTTP_404_NOT_FOUND
        mock_verify.assert_not_called()

    def test_mfa_disabled_raises_409(self, mock_db, step_up_store):
        user = MagicMock()
        with (
            patch("modules.auth.account_security.mfa_workflow_service.users_integration.get_user", return_value=user),
            patch(
                "modules.auth.account_security.mfa_workflow_service.mfa_integration.is_mfa_enabled_for_user",
                return_value=False,
            ),
            patch(
                "modules.auth.account_security.mfa_workflow_service.step_up_service.verify_step_up_credentials"
            ) as mock_verify,
            pytest.raises(core_exceptions.DomainError) as exc_info,
        ):
            mfa_workflow.generate_backup_codes(
                self._step_up(),
                MOCK_USER_ID,
                _SID,
                step_up_store,
                mock_db,
                revoke_other_sessions=False,
            )

        assert isinstance(exc_info.value, core_exceptions.ConflictError)
        assert exc_info.value.status_code == status.HTTP_409_CONFLICT
        mock_verify.assert_not_called()

    def test_step_up_failure_does_not_create_codes(self, mock_db, step_up_store):
        user = MagicMock()
        user.id = MOCK_USER_ID
        with (
            patch("modules.auth.account_security.mfa_workflow_service.users_integration.get_user", return_value=user),
            patch(
                "modules.auth.account_security.mfa_workflow_service.mfa_integration.is_mfa_enabled_for_user",
                return_value=True,
            ),
            patch(
                "modules.auth.account_security.mfa_workflow_service.step_up_service.verify_step_up_credentials",
                side_effect=core_exceptions.UnauthenticatedError("bad"),
            ),
            patch(
                "modules.auth.account_security.mfa_workflow_service.mfa_backup_codes_integration.create_backup_codes"
            ) as mock_create,
            pytest.raises(core_exceptions.DomainError) as exc_info,
        ):
            mfa_workflow.generate_backup_codes(
                self._step_up(),
                MOCK_USER_ID,
                _SID,
                step_up_store,
                mock_db,
                revoke_other_sessions=False,
            )

        assert exc_info.value.status_code == 401
        mock_create.assert_not_called()
