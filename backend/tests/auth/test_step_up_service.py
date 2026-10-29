"""Tests for auth.step_up_service."""

from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock, patch

import pytest
from jasil.backends.state_memory import MemoryState
from sqlalchemy.orm import Session

import core.exceptions as core_exceptions
import modules.auth.account_security.step_up_service as step_up_service
import modules.auth.account_security.step_up_store as step_up_store_module


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

    def read_ticket(self, ticket: str) -> None:
        """Return no ticket: these tests issue none."""
        return None

    def redeem_ticket(self, ticket: str) -> None:
        """Redeem no ticket: these tests issue none."""
        return None

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
        password_valid=True,
        step_up_store=None,
        db=None,
        mock_user=None,
        mfa_enabled=False,
        mfa_valid=True,
    ):
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
        password_hash = None
        if getattr(mock_user, "has_local_password", False):
            password_hash = mock_user.password

        with (
            patch(
                "modules.auth.account_security.step_up_service.users_integration.require_user",
                return_value=mock_user,
            ),
            patch(
                "modules.auth.account_security.step_up_service.credentials_integration.get_password_hash",
                return_value=password_hash,
            ),
            patch(
                "modules.auth.account_security.step_up_service.mfa_integration.is_mfa_enabled_for_user",
                return_value=mfa_enabled,
            ),
            patch(
                "modules.auth.account_security.step_up_service.mfa_integration.verify_user_mfa",
                return_value=mfa_valid,
            ),
            patch(
                "modules.auth.account_security.step_up_service.credentials_integration.verify_password",
                return_value=password_valid,
            ),
        ):
            return step_up_service.verify_step_up_credentials(
                user_id,
                current_password,
                mfa_code,
                step_up_store,
                db,
            )

    # ----------------------------------------------------------------
    # Lockout enforcement
    # ----------------------------------------------------------------

    def test_locked_out_raises_429(self):
        store = FakeStepUpStore()
        store.set_locked("user:1", seconds=300)

        with pytest.raises(core_exceptions.DomainError) as exc:
            self._call(user_id=1, step_up_store=store)

        assert exc.value.status_code == 429

    def test_locked_out_carries_retry_time(self):
        store = FakeStepUpStore()
        store.set_locked("user:1", seconds=300)

        with pytest.raises(core_exceptions.DomainError) as exc:
            self._call(user_id=1, step_up_store=store)

        assert isinstance(exc.value, core_exceptions.TooManyRequestsError)
        assert exc.value.retry_at is not None

    def test_lockout_not_applied_when_not_locked(self):
        # Should not raise 429
        store = FakeStepUpStore()
        mock_user = MagicMock()
        mock_user.password = "hashed"
        mock_user.has_local_password = True
        self._call(user_id=1, step_up_store=store, mock_user=mock_user, current_password="correct")

    # ----------------------------------------------------------------
    # SSO-only accounts (no local password)
    # ----------------------------------------------------------------

    def _sso_user(self):
        mock_user = MagicMock()
        mock_user.password = None
        mock_user.has_local_password = False
        return mock_user

    def test_sso_without_reauth_proof_is_refused_with_the_idp_challenge(self):
        """An SSO-only account must prove a fresh provider sign-in; no credentials is not a pass."""
        with pytest.raises(core_exceptions.IdpReauthRequiredError) as exc:
            self._call(mock_user=self._sso_user(), step_up_store=FakeStepUpStore())

        assert exc.value.status_code == 401
        assert exc.value.code == "idp-reauth-required"

    def test_sso_challenge_is_not_counted_as_a_failure(self):
        store = FakeStepUpStore()
        store._attempts["user:1"] = 3

        with pytest.raises(core_exceptions.IdpReauthRequiredError):
            self._call(user_id=1, mock_user=self._sso_user(), step_up_store=store)

        assert store._attempts["user:1"] == 3

    @pytest.mark.parametrize(
        ("mfa_code", "mfa_valid"),
        [(None, True), ("wrong", False), ("123456", True)],
        ids=["missing-code", "wrong-code", "correct-code"],
    )
    def test_sso_with_mfa_is_still_refused_without_reauth_proof(self, mfa_code, mfa_valid):
        """A valid MFA code alone never substitutes for the identity-provider sign-in."""
        store = FakeStepUpStore()

        with pytest.raises(core_exceptions.IdpReauthRequiredError):
            self._call(
                user_id=1,
                mock_user=self._sso_user(),
                step_up_store=store,
                mfa_enabled=True,
                mfa_code=mfa_code,
                mfa_valid=mfa_valid,
            )

        assert store._attempts.get("user:1", 0) == 0

    # ----------------------------------------------------------------
    # Accounts with local password
    # ----------------------------------------------------------------

    def test_password_missing_raises_401(self):
        mock_user = MagicMock()
        mock_user.password = "hashed"
        mock_user.has_local_password = True
        store = FakeStepUpStore()

        with pytest.raises(core_exceptions.DomainError) as exc:
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

        with pytest.raises(core_exceptions.DomainError):
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
        password_valid = False
        store = FakeStepUpStore()

        with pytest.raises(core_exceptions.DomainError) as exc:
            self._call(
                mock_user=mock_user,
                password_valid=password_valid,
                step_up_store=store,
                current_password="wrong",
            )

        assert exc.value.status_code == 401

    def test_password_wrong_records_failure(self):
        mock_user = MagicMock()
        mock_user.password = "hashed"
        mock_user.has_local_password = True
        password_valid = False
        store = FakeStepUpStore()

        with pytest.raises(core_exceptions.DomainError):
            self._call(
                user_id=1,
                mock_user=mock_user,
                password_valid=password_valid,
                step_up_store=store,
                current_password="wrong",
            )

        assert store._attempts.get("user:1", 0) == 1

    def test_password_correct_no_mfa_success(self):
        mock_user = MagicMock()
        mock_user.password = "hashed"
        mock_user.has_local_password = True
        password_valid = True
        store = FakeStepUpStore()

        self._call(
            mock_user=mock_user,
            password_valid=password_valid,
            step_up_store=store,
            current_password="correct",
            mfa_enabled=False,
        )

    def test_password_correct_no_mfa_resets_attempts(self):
        mock_user = MagicMock()
        mock_user.password = "hashed"
        mock_user.has_local_password = True
        password_valid = True
        store = FakeStepUpStore()
        store._attempts["user:1"] = 4

        self._call(
            user_id=1,
            mock_user=mock_user,
            password_valid=password_valid,
            step_up_store=store,
            current_password="correct",
            mfa_enabled=False,
        )

        assert "user:1" not in store._attempts

    def test_password_correct_mfa_missing_code_raises_401(self):
        mock_user = MagicMock()
        mock_user.password = "hashed"
        mock_user.has_local_password = True
        password_valid = True
        store = FakeStepUpStore()

        with pytest.raises(core_exceptions.DomainError) as exc:
            self._call(
                mock_user=mock_user,
                password_valid=password_valid,
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
        password_valid = True
        store = FakeStepUpStore()

        with pytest.raises(core_exceptions.DomainError):
            self._call(
                user_id=1,
                mock_user=mock_user,
                password_valid=password_valid,
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
        password_valid = True
        store = FakeStepUpStore()

        self._call(
            mock_user=mock_user,
            password_valid=password_valid,
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
        password_valid = True
        store = FakeStepUpStore()

        with pytest.raises(core_exceptions.DomainError) as exc:
            self._call(
                mock_user=mock_user,
                password_valid=password_valid,
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
        password_valid = True
        store = FakeStepUpStore()

        with pytest.raises(core_exceptions.DomainError):
            self._call(
                user_id=1,
                mock_user=mock_user,
                password_valid=password_valid,
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
        store = step_up_store_module.StepUpAttempts(MemoryState())
        key = "user:99"
        for _ in range(5):
            store.record_failed_attempt(key)

        assert store.is_locked_out(key)

    def test_lockout_cleared_on_success(self):
        mock_user = MagicMock()
        mock_user.password = "hashed"
        mock_user.has_local_password = True
        password_valid = True
        store = step_up_store_module.StepUpAttempts(MemoryState())
        key = "user:1"
        # Pre-load 3 failures (below threshold)
        for _ in range(3):
            store.record_failed_attempt(key)

        self._call(
            user_id=1,
            mock_user=mock_user,
            password_valid=password_valid,
            step_up_store=store,
            current_password="correct",
            mfa_enabled=False,
        )

        assert not store.is_locked_out(key)
        # The counter was reset: the next failure starts again at 1.
        assert store.record_failed_attempt(key) == 1
