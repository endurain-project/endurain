"""Tests for auth.step_up_service."""

from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException
from sqlalchemy.orm import Session

import auth._internal.security_stores as security_stores
import auth.services.step_up_service as step_up_service


class FakeStepUpStore:
    """
    In-memory step-up store test double.

    Attributes:
        _locked: Mapping of key to lockout expiry.
        _attempts: Mapping of key to attempt count.
    """

    def __init__(self) -> None:
        """Initialize the fake step-up store."""
        self._locked: dict[str, datetime] = {}
        self._attempts: dict[str, int] = {}

    def is_locked_out(self, key: str) -> bool:
        """Return True when key has an active lockout."""
        if key not in self._locked:
            return False
        if datetime.now(UTC) > self._locked[key]:
            del self._locked[key]
            return False
        return True

    def get_lockout_time(self, key: str) -> datetime | None:
        """Return lockout expiry datetime."""
        return self._locked.get(key)

    def record_failed_attempt(self, key: str) -> int:
        """Increment and return the attempt count."""
        self._attempts[key] = self._attempts.get(key, 0) + 1
        return self._attempts[key]

    def reset_attempts(self, key: str) -> None:
        """Clear the attempt counter."""
        self._attempts.pop(key, None)
        self._locked.pop(key, None)

    def set_locked(self, key: str, seconds: int = 300) -> None:
        """Helper to pre-set a lockout for a key."""
        self._locked[key] = datetime.now(UTC) + timedelta(seconds=seconds)


class TestStepUpKey:
    """_step_up_key: key format for user-based lockout."""

    def test_format(self):
        assert step_up_service._step_up_key(42) == "user:42"

    def test_unique_per_user(self):
        assert step_up_service._step_up_key(1) != step_up_service._step_up_key(2)


class TestVerifyStepUpCredentials:
    """verify_step_up_credentials: auth-owned step-up with lockout."""

    def _call(
        self,
        user_id=1,
        current_password=None,
        mfa_code=None,
        identity_service=None,
        step_up_store=None,
        db=None,
        mock_user=None,
        mfa_enabled=False,
        mfa_valid=True,
    ):
        if identity_service is None:
            identity_service = MagicMock()
        if step_up_store is None:
            step_up_store = FakeStepUpStore()
        if db is None:
            db = MagicMock(spec=Session)
        if mock_user is None:
            mock_user = MagicMock()
            mock_user.password = None
            mock_user.has_local_password = False

        # Derive the credential lookup result from the mock user: a local
        # password means a credential row exists carrying that hash.
        credential = None
        if getattr(mock_user, "has_local_password", False):
            credential = MagicMock()
            credential.password_hash = mock_user.password

        with (
            patch(
                "auth.services.step_up_service.users_utils.get_user_by_id_or_404",
                return_value=mock_user,
            ),
            patch(
                "auth.services.step_up_service.auth_credentials_crud.get_credential",
                return_value=credential,
            ),
            patch(
                "auth.services.step_up_service.mfa_service.is_mfa_enabled_for_user",
                return_value=mfa_enabled,
            ),
            patch(
                "auth.services.step_up_service.mfa_service.verify_user_mfa",
                return_value=mfa_valid,
            ),
        ):
            return step_up_service.verify_step_up_credentials(
                user_id,
                current_password,
                mfa_code,
                identity_service,
                step_up_store,
                db,
            )

    # ----------------------------------------------------------------
    # Lockout enforcement
    # ----------------------------------------------------------------

    def test_locked_out_raises_429(self):
        store = FakeStepUpStore()
        store.set_locked("user:1", seconds=300)

        with pytest.raises(HTTPException) as exc:
            self._call(user_id=1, step_up_store=store)

        assert exc.value.status_code == 429

    def test_locked_out_includes_retry_after_header(self):
        store = FakeStepUpStore()
        store.set_locked("user:1", seconds=300)

        with pytest.raises(HTTPException) as exc:
            self._call(user_id=1, step_up_store=store)

        assert "Retry-After" in exc.value.headers
        assert int(exc.value.headers["Retry-After"]) > 0

    def test_lockout_not_applied_when_not_locked(self):
        # Should not raise 429
        store = FakeStepUpStore()
        mock_user = MagicMock()
        mock_user.password = None
        mock_user.has_local_password = False
        # No password, no MFA → success path
        self._call(user_id=1, step_up_store=store, mock_user=mock_user)

    # ----------------------------------------------------------------
    # SSO-only accounts (no local password)
    # ----------------------------------------------------------------

    def test_sso_no_mfa_success(self):
        """SSO-only accounts pass step-up with no credentials supplied.

        Password factor is skipped when db_user.password is None because
        there is no local credential to verify against. This is the
        intended behavior; a future IdP re-auth flow would close the gap.
        See verify_step_up_credentials docstring for the known coverage note.
        """
        mock_user = MagicMock()
        mock_user.password = None
        mock_user.has_local_password = False
        store = FakeStepUpStore()
        self._call(mock_user=mock_user, step_up_store=store)

    def test_sso_no_mfa_resets_attempts_on_success(self):
        """A successful SSO-only step-up clears any prior failed-attempt counter."""
        mock_user = MagicMock()
        mock_user.password = None
        mock_user.has_local_password = False
        store = FakeStepUpStore()
        store._attempts["user:1"] = 3

        self._call(user_id=1, mock_user=mock_user, step_up_store=store)

        assert "user:1" not in store._attempts

    def test_sso_mfa_missing_code_raises_401(self):
        """SSO-only accounts still require MFA when it is enabled.

        Even though the password factor is skipped, an enrolled MFA code
        must still be supplied. Omitting it raises 401.
        """
        mock_user = MagicMock()
        mock_user.password = None
        mock_user.has_local_password = False
        store = FakeStepUpStore()

        with pytest.raises(HTTPException) as exc:
            self._call(
                mock_user=mock_user,
                step_up_store=store,
                mfa_enabled=True,
                mfa_code=None,
            )

        assert exc.value.status_code == 401
        assert exc.value.detail == "MFA code required for this operation"

    def test_sso_mfa_missing_code_records_failure(self):
        mock_user = MagicMock()
        mock_user.password = None
        mock_user.has_local_password = False
        store = FakeStepUpStore()

        with pytest.raises(HTTPException):
            self._call(
                user_id=1,
                mock_user=mock_user,
                step_up_store=store,
                mfa_enabled=True,
                mfa_code=None,
            )

        assert store._attempts.get("user:1", 0) == 1

    def test_sso_mfa_wrong_code_raises_401(self):
        mock_user = MagicMock()
        mock_user.password = None
        mock_user.has_local_password = False
        store = FakeStepUpStore()

        with pytest.raises(HTTPException) as exc:
            self._call(
                mock_user=mock_user,
                step_up_store=store,
                mfa_enabled=True,
                mfa_code="wrong",
                mfa_valid=False,
            )

        assert exc.value.status_code == 401

    def test_sso_mfa_wrong_code_records_failure(self):
        mock_user = MagicMock()
        mock_user.password = None
        mock_user.has_local_password = False
        store = FakeStepUpStore()

        with pytest.raises(HTTPException):
            self._call(
                user_id=1,
                mock_user=mock_user,
                step_up_store=store,
                mfa_enabled=True,
                mfa_code="wrong",
                mfa_valid=False,
            )

        assert store._attempts.get("user:1", 0) == 1

    def test_sso_mfa_correct_code_success(self):
        """SSO-only account with MFA enabled passes when valid MFA code is provided."""
        mock_user = MagicMock()
        mock_user.password = None
        mock_user.has_local_password = False
        store = FakeStepUpStore()

        self._call(
            mock_user=mock_user,
            step_up_store=store,
            mfa_enabled=True,
            mfa_code="123456",
            mfa_valid=True,
        )

    # ----------------------------------------------------------------
    # Accounts with local password
    # ----------------------------------------------------------------

    def test_password_missing_raises_401(self):
        mock_user = MagicMock()
        mock_user.password = "hashed"
        mock_user.has_local_password = True
        store = FakeStepUpStore()

        with pytest.raises(HTTPException) as exc:
            self._call(
                mock_user=mock_user,
                step_up_store=store,
                current_password=None,
            )

        assert exc.value.status_code == 401

    def test_password_missing_records_failure(self):
        mock_user = MagicMock()
        mock_user.password = "hashed"
        mock_user.has_local_password = True
        store = FakeStepUpStore()

        with pytest.raises(HTTPException):
            self._call(
                user_id=1,
                mock_user=mock_user,
                step_up_store=store,
                current_password=None,
            )

        assert store._attempts.get("user:1", 0) == 1

    def test_password_wrong_raises_401(self):
        mock_user = MagicMock()
        mock_user.password = "hashed"
        mock_user.has_local_password = True
        identity_service = MagicMock()
        identity_service.verify_password.return_value = False
        store = FakeStepUpStore()

        with pytest.raises(HTTPException) as exc:
            self._call(
                mock_user=mock_user,
                identity_service=identity_service,
                step_up_store=store,
                current_password="wrong",
            )

        assert exc.value.status_code == 401

    def test_password_wrong_records_failure(self):
        mock_user = MagicMock()
        mock_user.password = "hashed"
        mock_user.has_local_password = True
        identity_service = MagicMock()
        identity_service.verify_password.return_value = False
        store = FakeStepUpStore()

        with pytest.raises(HTTPException):
            self._call(
                user_id=1,
                mock_user=mock_user,
                identity_service=identity_service,
                step_up_store=store,
                current_password="wrong",
            )

        assert store._attempts.get("user:1", 0) == 1

    def test_password_correct_no_mfa_success(self):
        mock_user = MagicMock()
        mock_user.password = "hashed"
        mock_user.has_local_password = True
        identity_service = MagicMock()
        identity_service.verify_password.return_value = True
        store = FakeStepUpStore()

        self._call(
            mock_user=mock_user,
            identity_service=identity_service,
            step_up_store=store,
            current_password="correct",
            mfa_enabled=False,
        )

    def test_password_correct_no_mfa_resets_attempts(self):
        mock_user = MagicMock()
        mock_user.password = "hashed"
        mock_user.has_local_password = True
        identity_service = MagicMock()
        identity_service.verify_password.return_value = True
        store = FakeStepUpStore()
        store._attempts["user:1"] = 4

        self._call(
            user_id=1,
            mock_user=mock_user,
            identity_service=identity_service,
            step_up_store=store,
            current_password="correct",
            mfa_enabled=False,
        )

        assert "user:1" not in store._attempts

    def test_password_correct_mfa_missing_code_raises_401(self):
        mock_user = MagicMock()
        mock_user.password = "hashed"
        mock_user.has_local_password = True
        identity_service = MagicMock()
        identity_service.verify_password.return_value = True
        store = FakeStepUpStore()

        with pytest.raises(HTTPException) as exc:
            self._call(
                mock_user=mock_user,
                identity_service=identity_service,
                step_up_store=store,
                current_password="correct",
                mfa_enabled=True,
                mfa_code=None,
            )

        assert exc.value.status_code == 401
        assert exc.value.detail == "MFA code required for this operation"

    def test_password_correct_mfa_missing_records_failure(self):
        mock_user = MagicMock()
        mock_user.password = "hashed"
        mock_user.has_local_password = True
        identity_service = MagicMock()
        identity_service.verify_password.return_value = True
        store = FakeStepUpStore()

        with pytest.raises(HTTPException):
            self._call(
                user_id=1,
                mock_user=mock_user,
                identity_service=identity_service,
                step_up_store=store,
                current_password="correct",
                mfa_enabled=True,
                mfa_code=None,
            )

        assert store._attempts.get("user:1", 0) == 1

    def test_password_correct_mfa_correct_code_success(self):
        mock_user = MagicMock()
        mock_user.password = "hashed"
        mock_user.has_local_password = True
        identity_service = MagicMock()
        identity_service.verify_password.return_value = True
        store = FakeStepUpStore()

        self._call(
            mock_user=mock_user,
            identity_service=identity_service,
            step_up_store=store,
            current_password="correct",
            mfa_enabled=True,
            mfa_code="123456",
            mfa_valid=True,
        )

    def test_password_correct_mfa_wrong_code_raises_401(self):
        mock_user = MagicMock()
        mock_user.password = "hashed"
        mock_user.has_local_password = True
        identity_service = MagicMock()
        identity_service.verify_password.return_value = True
        store = FakeStepUpStore()

        with pytest.raises(HTTPException) as exc:
            self._call(
                mock_user=mock_user,
                identity_service=identity_service,
                step_up_store=store,
                current_password="correct",
                mfa_enabled=True,
                mfa_code="wrong",
                mfa_valid=False,
            )

        assert exc.value.status_code == 401

    def test_password_correct_mfa_wrong_records_failure(self):
        mock_user = MagicMock()
        mock_user.password = "hashed"
        mock_user.has_local_password = True
        identity_service = MagicMock()
        identity_service.verify_password.return_value = True
        store = FakeStepUpStore()

        with pytest.raises(HTTPException):
            self._call(
                user_id=1,
                mock_user=mock_user,
                identity_service=identity_service,
                step_up_store=store,
                current_password="correct",
                mfa_enabled=True,
                mfa_code="wrong",
                mfa_valid=False,
            )

        assert store._attempts.get("user:1", 0) == 1

    # ----------------------------------------------------------------
    # Progressive lockout thresholds (in-memory store)
    # ----------------------------------------------------------------

    def test_lockout_applied_after_threshold(self):
        store = security_stores.StepUpAttempts()
        key = "user:99"
        for _ in range(5):
            store.record_failed_attempt(key)

        assert store.is_locked_out(key)

    def test_lockout_cleared_on_success(self):
        mock_user = MagicMock()
        mock_user.password = None
        mock_user.has_local_password = False
        identity_service = MagicMock()
        store = security_stores.StepUpAttempts()
        key = "user:1"
        # Pre-load 3 failures (below threshold)
        for _ in range(3):
            store.record_failed_attempt(key)

        self._call(
            user_id=1,
            mock_user=mock_user,
            identity_service=identity_service,
            step_up_store=store,
            mfa_enabled=False,
        )

        assert not store.is_locked_out(key)
        # The counter was reset: the next failure starts again at 1.
        assert store.record_failed_attempt(key) == 1
