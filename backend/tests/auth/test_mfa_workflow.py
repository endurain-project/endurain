"""Tests for auth._internal.services.mfa_workflow.

mfa_workflow is the security-critical route-facing facade profile routes call.
It owns step-up verification, the pending setup-secret store, and response
shaping while orchestrating the lower-level ``modules.auth.mfa.service`` /
``modules.auth.mfa.backup_codes.crud`` helpers.

These tests mock the lower-level helpers (patched at the
``modules.auth._internal.services.mfa_workflow`` namespace) and assert the orchestration
behaviour: delegation arguments, step-up enforcement, the pending-secret
store lifecycle, error propagation, and response/schema shaping.
"""

from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException, status

import modules.auth._internal.services.mfa_workflow as mfa_workflow
import modules.auth.mfa.schema as mfa_schema
import modules.users.users.schema as users_schema


@pytest.fixture
def identity_service() -> MagicMock:
    """Return a mock IdentityService."""
    return MagicMock()


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
            "modules.auth._internal.services.mfa_workflow.mfa_service.is_mfa_enabled_for_user",
            return_value=True,
        ) as mock_is_enabled:
            result = mfa_workflow.get_mfa_status(7, mock_db)

        mock_is_enabled.assert_called_once_with(7, mock_db)
        assert isinstance(result, mfa_schema.MFAStatusResponse)
        assert result.mfa_enabled is True

    def test_returns_enabled_false(self, mock_db):
        with patch(
            "modules.auth._internal.services.mfa_workflow.mfa_service.is_mfa_enabled_for_user",
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
            "modules.auth._internal.services.mfa_workflow.mfa_backup_codes_crud.get_user_backup_codes",
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
            "modules.auth._internal.services.mfa_workflow.mfa_backup_codes_crud.get_user_backup_codes",
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
            "modules.auth._internal.services.mfa_workflow.mfa_service.setup_user_mfa",
            return_value=response,
        ) as mock_setup:
            result = mfa_workflow.setup_mfa(7, mock_db, mfa_secret_store)

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

    def test_happy_path_enables_and_clears_pending_secret(
        self, mock_db, identity_service, step_up_store, mfa_secret_store
    ):
        mfa_secret_store.get_secret.return_value = "pending-secret"
        with (
            patch(
                "modules.auth._internal.services.mfa_workflow.step_up_service.verify_step_up_credentials"
            ) as mock_verify,
            patch(
                "modules.auth._internal.services.mfa_workflow.mfa_service.enable_user_mfa",
                return_value=["code-1", "code-2"],
            ) as mock_enable,
            patch("modules.auth._internal.services.mfa_workflow.logger") as mock_log,
        ):
            result = mfa_workflow.enable_mfa(
                self._request(),
                7,
                identity_service,
                step_up_store,
                mock_db,
                mfa_secret_store,
            )

        mock_verify.assert_called_once_with(
            7,
            "old-pass",
            None,
            identity_service,
            step_up_store,
            mock_db,
        )
        mock_enable.assert_called_once_with(7, "pending-secret", "123456", identity_service, mock_db)
        mfa_secret_store.delete_secret.assert_called_once_with(7)
        assert len(mock_log.method_calls) == 1
        assert result == {"message": "MFA enabled successfully", "backup_codes": ["code-1", "code-2"]}

    def test_step_up_failure_propagates_before_secret_lookup(
        self, mock_db, identity_service, step_up_store, mfa_secret_store
    ):
        with (
            patch(
                "modules.auth._internal.services.mfa_workflow.step_up_service.verify_step_up_credentials",
                side_effect=HTTPException(status_code=401, detail="bad password"),
            ),
            patch("modules.auth._internal.services.mfa_workflow.mfa_service.enable_user_mfa") as mock_enable,
            pytest.raises(HTTPException) as exc_info,
        ):
            mfa_workflow.enable_mfa(
                self._request(),
                7,
                identity_service,
                step_up_store,
                mock_db,
                mfa_secret_store,
            )

        assert exc_info.value.status_code == 401
        mfa_secret_store.get_secret.assert_not_called()
        mock_enable.assert_not_called()

    def test_no_pending_secret_raises_400(self, mock_db, identity_service, step_up_store, mfa_secret_store):
        mfa_secret_store.get_secret.return_value = None
        with (
            patch("modules.auth._internal.services.mfa_workflow.step_up_service.verify_step_up_credentials"),
            patch("modules.auth._internal.services.mfa_workflow.mfa_service.enable_user_mfa") as mock_enable,
            pytest.raises(HTTPException) as exc_info,
        ):
            mfa_workflow.enable_mfa(
                self._request(),
                7,
                identity_service,
                step_up_store,
                mock_db,
                mfa_secret_store,
            )

        assert exc_info.value.status_code == status.HTTP_400_BAD_REQUEST
        mock_enable.assert_not_called()
        mfa_secret_store.delete_secret.assert_not_called()

    def test_invalid_mfa_code_keeps_pending_secret_for_retry(
        self, mock_db, identity_service, step_up_store, mfa_secret_store
    ):
        """A wrong TOTP code must NOT discard the pending secret (allow retry)."""
        mfa_secret_store.get_secret.return_value = "pending-secret"
        with (
            patch("modules.auth._internal.services.mfa_workflow.step_up_service.verify_step_up_credentials"),
            patch(
                "modules.auth._internal.services.mfa_workflow.mfa_service.enable_user_mfa",
                side_effect=HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid MFA code"),
            ),
            pytest.raises(HTTPException) as exc_info,
        ):
            mfa_workflow.enable_mfa(
                self._request(),
                7,
                identity_service,
                step_up_store,
                mock_db,
                mfa_secret_store,
            )

        assert exc_info.value.detail == "Invalid MFA code"
        mfa_secret_store.delete_secret.assert_not_called()

    def test_other_enable_error_discards_pending_secret(
        self, mock_db, identity_service, step_up_store, mfa_secret_store
    ):
        """Any non-"Invalid MFA code" failure clears the pending secret."""
        mfa_secret_store.get_secret.return_value = "pending-secret"
        with (
            patch("modules.auth._internal.services.mfa_workflow.step_up_service.verify_step_up_credentials"),
            patch(
                "modules.auth._internal.services.mfa_workflow.mfa_service.enable_user_mfa",
                side_effect=HTTPException(status_code=status.HTTP_409_CONFLICT, detail="MFA already enabled"),
            ),
            pytest.raises(HTTPException) as exc_info,
        ):
            mfa_workflow.enable_mfa(
                self._request(),
                7,
                identity_service,
                step_up_store,
                mock_db,
                mfa_secret_store,
            )

        assert exc_info.value.status_code == status.HTTP_409_CONFLICT
        mfa_secret_store.delete_secret.assert_called_once_with(7)

    def test_invalid_mfa_code_with_non_400_status_discards_secret(
        self, mock_db, identity_service, step_up_store, mfa_secret_store
    ):
        """Same detail but a non-400 status still discards the pending secret."""
        mfa_secret_store.get_secret.return_value = "pending-secret"
        with (
            patch("modules.auth._internal.services.mfa_workflow.step_up_service.verify_step_up_credentials"),
            patch(
                "modules.auth._internal.services.mfa_workflow.mfa_service.enable_user_mfa",
                side_effect=HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid MFA code"),
            ),
            pytest.raises(HTTPException),
        ):
            mfa_workflow.enable_mfa(
                self._request(),
                7,
                identity_service,
                step_up_store,
                mock_db,
                mfa_secret_store,
            )

        mfa_secret_store.delete_secret.assert_called_once_with(7)


# ---------------------------------------------------------------------------
# disable_mfa
# ---------------------------------------------------------------------------


class TestDisableMfa:
    """disable_mfa requires step-up (password + MFA code)."""

    def _request(self) -> mfa_schema.MFADisableRequest:
        return mfa_schema.MFADisableRequest(mfa_code="123456", current_password="old-pass")

    def test_happy_path_disables_after_step_up(self, mock_db, identity_service, step_up_store):
        with (
            patch(
                "modules.auth._internal.services.mfa_workflow.step_up_service.verify_step_up_credentials"
            ) as mock_verify,
            patch("modules.auth._internal.services.mfa_workflow.mfa_service.disable_user_mfa") as mock_disable,
            patch("modules.auth._internal.services.mfa_workflow.logger") as mock_log,
        ):
            result = mfa_workflow.disable_mfa(
                self._request(),
                7,
                identity_service,
                step_up_store,
                mock_db,
            )

        mock_verify.assert_called_once_with(
            7,
            "old-pass",
            "123456",
            identity_service,
            step_up_store,
            mock_db,
        )
        mock_disable.assert_called_once_with(7, mock_db)
        assert len(mock_log.method_calls) == 1
        assert result == {"message": "MFA disabled successfully"}

    def test_step_up_failure_does_not_disable(self, mock_db, identity_service, step_up_store):
        with (
            patch(
                "modules.auth._internal.services.mfa_workflow.step_up_service.verify_step_up_credentials",
                side_effect=HTTPException(status_code=401, detail="bad"),
            ),
            patch("modules.auth._internal.services.mfa_workflow.mfa_service.disable_user_mfa") as mock_disable,
            pytest.raises(HTTPException) as exc_info,
        ):
            mfa_workflow.disable_mfa(
                self._request(),
                7,
                identity_service,
                step_up_store,
                mock_db,
            )

        assert exc_info.value.status_code == 401
        mock_disable.assert_not_called()


# ---------------------------------------------------------------------------
# verify_mfa
# ---------------------------------------------------------------------------


class TestVerifyMfa:
    """verify_mfa validates a code for the authenticated user."""

    def _request(self) -> mfa_schema.MFARequest:
        return mfa_schema.MFARequest(mfa_code="123456")

    def test_valid_code_returns_success(self, mock_db, identity_service):
        with patch(
            "modules.auth._internal.services.mfa_workflow.mfa_service.verify_user_mfa",
            return_value=True,
        ) as mock_verify:
            result = mfa_workflow.verify_mfa(self._request(), 7, identity_service, mock_db)

        mock_verify.assert_called_once_with(7, "123456", identity_service, mock_db)
        assert result == {"message": "MFA code verified successfully"}

    def test_invalid_code_raises_400(self, mock_db, identity_service):
        with (
            patch(
                "modules.auth._internal.services.mfa_workflow.mfa_service.verify_user_mfa",
                return_value=False,
            ),
            pytest.raises(HTTPException) as exc_info,
        ):
            mfa_workflow.verify_mfa(self._request(), 7, identity_service, mock_db)

        assert exc_info.value.status_code == status.HTTP_400_BAD_REQUEST
        assert exc_info.value.detail == "Invalid MFA code"


# ---------------------------------------------------------------------------
# generate_backup_codes
# ---------------------------------------------------------------------------


class TestGenerateBackupCodes:
    """generate_backup_codes gates on user existence, MFA state, and step-up."""

    def _step_up(self) -> users_schema.StepUpVerification:
        return users_schema.StepUpVerification(current_password="old-pass", mfa_code="123456")

    def test_happy_path_returns_codes(self, mock_db, identity_service, step_up_store):
        user = MagicMock()
        user.id = 7
        user.mfa_enabled = True
        with (
            patch("modules.auth._internal.services.mfa_workflow.users_crud.get_user_by_id", return_value=user),
            patch(
                "modules.auth._internal.services.mfa_workflow.step_up_service.verify_step_up_credentials"
            ) as mock_verify,
            patch(
                "modules.auth._internal.services.mfa_workflow.mfa_backup_codes_crud.create_backup_codes",
                return_value=["a", "b", "c"],
            ) as mock_create,
            patch("modules.auth._internal.services.mfa_workflow.logger"),
        ):
            result = mfa_workflow.generate_backup_codes(
                self._step_up(),
                7,
                identity_service,
                step_up_store,
                mock_db,
            )

        mock_verify.assert_called_once_with(
            7,
            "old-pass",
            "123456",
            identity_service,
            step_up_store,
            mock_db,
        )
        mock_create.assert_called_once_with(7, identity_service, mock_db)
        assert result.codes == ["a", "b", "c"]
        assert result.created_at is not None

    def test_user_not_found_raises_404(self, mock_db, identity_service, step_up_store):
        with (
            patch("modules.auth._internal.services.mfa_workflow.users_crud.get_user_by_id", return_value=None),
            patch(
                "modules.auth._internal.services.mfa_workflow.step_up_service.verify_step_up_credentials"
            ) as mock_verify,
            pytest.raises(HTTPException) as exc_info,
        ):
            mfa_workflow.generate_backup_codes(
                self._step_up(),
                7,
                identity_service,
                step_up_store,
                mock_db,
            )

        assert exc_info.value.status_code == status.HTTP_404_NOT_FOUND
        mock_verify.assert_not_called()

    def test_mfa_disabled_raises_400(self, mock_db, identity_service, step_up_store):
        user = MagicMock()
        user.mfa_enabled = False
        with (
            patch("modules.auth._internal.services.mfa_workflow.users_crud.get_user_by_id", return_value=user),
            patch(
                "modules.auth._internal.services.mfa_workflow.step_up_service.verify_step_up_credentials"
            ) as mock_verify,
            pytest.raises(HTTPException) as exc_info,
        ):
            mfa_workflow.generate_backup_codes(
                self._step_up(),
                7,
                identity_service,
                step_up_store,
                mock_db,
            )

        assert exc_info.value.status_code == status.HTTP_400_BAD_REQUEST
        mock_verify.assert_not_called()

    def test_step_up_failure_does_not_create_codes(self, mock_db, identity_service, step_up_store):
        user = MagicMock()
        user.id = 7
        user.mfa_enabled = True
        with (
            patch("modules.auth._internal.services.mfa_workflow.users_crud.get_user_by_id", return_value=user),
            patch(
                "modules.auth._internal.services.mfa_workflow.step_up_service.verify_step_up_credentials",
                side_effect=HTTPException(status_code=401, detail="bad"),
            ),
            patch(
                "modules.auth._internal.services.mfa_workflow.mfa_backup_codes_crud.create_backup_codes"
            ) as mock_create,
            pytest.raises(HTTPException) as exc_info,
        ):
            mfa_workflow.generate_backup_codes(
                self._step_up(),
                7,
                identity_service,
                step_up_store,
                mock_db,
            )

        assert exc_info.value.status_code == 401
        mock_create.assert_not_called()
