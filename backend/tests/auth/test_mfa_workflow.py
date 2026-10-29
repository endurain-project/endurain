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

from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest
from fastapi import status

import core.exceptions as core_exceptions
import modules.auth.account_security.mfa_workflow_service as mfa_workflow
import modules.auth.credentials.integration_service as credentials_integration
import modules.auth.mfa.schema as mfa_schema
import modules.users.users.schema as users_schema


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
            result = mfa_workflow.get_mfa_status(7, mock_db)

        mock_is_enabled.assert_called_once_with(7, mock_db)
        assert isinstance(result, mfa_schema.MFAStatusRead)
        assert result.mfa_enabled is True

    def test_returns_enabled_false(self, mock_db):
        with patch(
            "modules.auth.account_security.mfa_workflow_service.mfa_integration.is_mfa_enabled_for_user",
            return_value=False,
        ):
            result = mfa_workflow.get_mfa_status(7, mock_db)

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
            result = mfa_workflow.get_backup_code_status(7, mock_db)

        mock_get.assert_called_once_with(7, mock_db)
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
            result = mfa_workflow.get_backup_code_status(7, mock_db)

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
            result = mfa_workflow.setup_mfa(7, mfa_secret_store, mock_db)

        mock_setup.assert_called_once_with(7, mock_db)
        mfa_secret_store.add_secret.assert_called_once_with(7, "TOTPSECRET")
        assert result is response


# ---------------------------------------------------------------------------
# enable_mfa
# ---------------------------------------------------------------------------


class TestEnableMfa:
    """enable_mfa enforces step-up, consumes pending secret, owns cleanup."""

    def _request(self) -> mfa_schema.MFASetupRequest:
        return mfa_schema.MFASetupRequest(mfa_code="123456", current_password="old-pass")

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
            patch("modules.auth.account_security.mfa_workflow_service.logger") as mock_log,
        ):
            result = mfa_workflow.enable_mfa(
                self._request(),
                7,
                step_up_store,
                mfa_secret_store,
                mock_db,
            )

        mock_verify.assert_called_once_with(
            7,
            "old-pass",
            None,
            step_up_store,
            mock_db,
        )
        mock_enable.assert_called_once_with(7, "pending-secret", "123456", credentials_integration, mock_db)
        mfa_secret_store.delete_secret.assert_called_once_with(7)
        assert len(mock_log.method_calls) == 1
        assert isinstance(result, mfa_schema.MFAEnableRead)
        assert result.model_dump() == {"message": "MFA enabled successfully", "backup_codes": ["code-1", "code-2"]}

    def test_step_up_failure_propagates_before_secret_lookup(self, mock_db, step_up_store, mfa_secret_store):
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
                7,
                step_up_store,
                mfa_secret_store,
                mock_db,
            )

        assert exc_info.value.status_code == 401
        mfa_secret_store.get_secret.assert_not_called()
        mock_enable.assert_not_called()

    def test_no_pending_secret_raises_400(self, mock_db, step_up_store, mfa_secret_store):
        mfa_secret_store.get_secret.return_value = None
        with (
            patch("modules.auth.account_security.mfa_workflow_service.step_up_service.verify_step_up_credentials"),
            patch("modules.auth.account_security.mfa_workflow_service.mfa_integration.enable_user_mfa") as mock_enable,
            pytest.raises(core_exceptions.DomainError) as exc_info,
        ):
            mfa_workflow.enable_mfa(
                self._request(),
                7,
                step_up_store,
                mfa_secret_store,
                mock_db,
            )

        assert exc_info.value.status_code == status.HTTP_400_BAD_REQUEST
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
                7,
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
                7,
                step_up_store,
                mfa_secret_store,
                mock_db,
            )

        assert exc_info.value.status_code == status.HTTP_409_CONFLICT
        mfa_secret_store.delete_secret.assert_called_once_with(7)

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
                7,
                step_up_store,
                mfa_secret_store,
                mock_db,
            )

        mfa_secret_store.delete_secret.assert_called_once_with(7)


# ---------------------------------------------------------------------------
# disable_mfa
# ---------------------------------------------------------------------------


class TestDisableMfa:
    """disable_mfa requires step-up (password + MFA code)."""

    def _request(self) -> mfa_schema.MFADisableRequest:
        return mfa_schema.MFADisableRequest(mfa_code="123456", current_password="old-pass")

    def test_happy_path_disables_after_step_up(self, mock_db, step_up_store):
        with (
            patch(
                "modules.auth.account_security.mfa_workflow_service.step_up_service.verify_step_up_credentials"
            ) as mock_verify,
            patch(
                "modules.auth.account_security.mfa_workflow_service.mfa_integration.disable_user_mfa"
            ) as mock_disable,
            patch("modules.auth.account_security.mfa_workflow_service.logger") as mock_log,
        ):
            result = mfa_workflow.disable_mfa(
                self._request(),
                7,
                step_up_store,
                mock_db,
            )

        mock_verify.assert_called_once_with(
            7,
            "old-pass",
            "123456",
            step_up_store,
            mock_db,
        )
        mock_disable.assert_called_once_with(7, mock_db)
        assert len(mock_log.method_calls) == 1
        assert isinstance(result, mfa_schema.MFADisableRead)
        assert result.model_dump() == {"message": "MFA disabled successfully"}

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
                7,
                step_up_store,
                mock_db,
            )

        assert exc_info.value.status_code == 401
        mock_disable.assert_not_called()


# ---------------------------------------------------------------------------
# verify_mfa
# ---------------------------------------------------------------------------


class TestVerifyMfa:
    """verify_mfa validates a code for the authenticated user, under the step-up lockout."""

    _VERIFY = "modules.auth.account_security.step_up_service.mfa_integration.verify_user_mfa"

    def _request(self) -> mfa_schema.MFARequest:
        return mfa_schema.MFARequest(mfa_code="123456")

    @pytest.fixture(autouse=True)
    def _not_locked_out(self, step_up_store):
        step_up_store.is_locked_out.return_value = False

    def test_valid_code_returns_success_and_clears_the_failures(self, mock_db, step_up_store):
        with patch(self._VERIFY, return_value=True) as mock_verify:
            result = mfa_workflow.verify_mfa(self._request(), 7, step_up_store, mock_db)

        mock_verify.assert_called_once_with(7, "123456", credentials_integration, mock_db, replay_guard=step_up_store)
        step_up_store.reset_attempts.assert_called_once_with("user:7")
        assert isinstance(result, mfa_schema.MFAVerifyRead)
        assert result.model_dump() == {"message": "MFA code verified successfully"}

    def test_invalid_code_raises_400_and_counts_the_failure(self, mock_db, step_up_store):
        step_up_store.record_failed_attempt.return_value = 1
        with (
            patch(self._VERIFY, return_value=False),
            pytest.raises(core_exceptions.DomainError) as exc_info,
        ):
            mfa_workflow.verify_mfa(self._request(), 7, step_up_store, mock_db)

        assert exc_info.value.status_code == status.HTTP_400_BAD_REQUEST
        assert exc_info.value.detail == "Invalid MFA code"
        step_up_store.record_failed_attempt.assert_called_once_with("user:7")

    def test_a_locked_out_user_is_refused_without_a_guess(self, mock_db, step_up_store):
        """A stolen access token must not allow unlimited guesses at the code."""
        step_up_store.is_locked_out.return_value = True
        step_up_store.get_lockout_time.return_value = None

        with (
            patch(self._VERIFY) as mock_verify,
            pytest.raises(core_exceptions.TooManyRequestsError),
        ):
            mfa_workflow.verify_mfa(self._request(), 7, step_up_store, mock_db)

        mock_verify.assert_not_called()


# ---------------------------------------------------------------------------
# generate_backup_codes
# ---------------------------------------------------------------------------


class TestGenerateBackupCodes:
    """generate_backup_codes gates on user existence, MFA state, and step-up."""

    def _step_up(self) -> users_schema.StepUpVerification:
        return users_schema.StepUpVerification(current_password="old-pass", mfa_code="123456")

    def test_happy_path_returns_codes(self, mock_db, step_up_store):
        user = MagicMock()
        user.id = 7
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
                7,
                step_up_store,
                mock_db,
            )

        mock_verify.assert_called_once_with(
            7,
            "old-pass",
            "123456",
            step_up_store,
            mock_db,
        )
        mock_create.assert_called_once_with(7, credentials_integration, mock_db)
        assert result.codes == ["a", "b", "c"]
        assert result.created_at is not None

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
                7,
                step_up_store,
                mock_db,
            )

        assert exc_info.value.status_code == status.HTTP_404_NOT_FOUND
        mock_verify.assert_not_called()

    def test_mfa_disabled_raises_400(self, mock_db, step_up_store):
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
                7,
                step_up_store,
                mock_db,
            )

        assert exc_info.value.status_code == status.HTTP_400_BAD_REQUEST
        mock_verify.assert_not_called()

    def test_step_up_failure_does_not_create_codes(self, mock_db, step_up_store):
        user = MagicMock()
        user.id = 7
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
                7,
                step_up_store,
                mock_db,
            )

        assert exc_info.value.status_code == 401
        mock_create.assert_not_called()
