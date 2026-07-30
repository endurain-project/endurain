"""Tests for MFA reads sourced from the ``users_mfa`` table.

Verifies that MFA logic in ``auth.mfa.service`` derives MFA state from the
``users_mfa`` row (resolved via ``auth_mfa_crud.get_user_mfa_row`` — directly
in ``verify_user_mfa`` and through ``is_mfa_enabled_for_user`` for
setup/enable/disable) rather than from any column on the ``users`` row.
"""

from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException, status

import auth.mfa.models as auth_mfa_models
import auth.mfa.service as mfa_service
import users.users.models as users_models

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_user(
    user_id: int = 1,
    mfa_enabled: bool = False,
    mfa_secret: str | None = None,
) -> MagicMock:
    """
    Return a mock Users row whose auth_mfa carries the given MFA state.

    The ``users_mfa`` row (``user.auth_mfa``) is the sole source of truth;
    production resolves it via ``auth_mfa_crud.get_user_mfa_row``.
    """
    mfa_row: MagicMock | None
    if mfa_enabled or mfa_secret:
        mfa_row = MagicMock(spec=auth_mfa_models.UsersMFA)
        mfa_row.mfa_enabled = mfa_enabled
        mfa_row.mfa_secret = mfa_secret
    else:
        mfa_row = None

    user = MagicMock(spec=users_models.Users)
    user.id = user_id
    user.username = "testuser"
    # Source of truth: the users_mfa row
    user.auth_mfa = mfa_row
    return user


def _patch_get_user(user: MagicMock) -> Any:
    """Patch users_utils.get_user_by_id_or_404 to return a user."""
    return patch(
        "auth.mfa.service.users_utils.get_user_by_id_or_404",
        return_value=user,
    )


@pytest.fixture(autouse=True)
def _wire_mfa_row():
    """Resolve ``auth_mfa_crud.get_user_mfa_row`` from the patched user mock.

    Production derives MFA state from the ``users_mfa`` row via
    ``auth_mfa_crud.get_user_mfa_row`` — directly in ``verify_user_mfa`` and
    through ``is_mfa_enabled_for_user`` for setup/enable/disable. Resolve that
    row from the patched user's ``auth_mfa`` so these tests keep exercising the
    ``users_mfa``-as-source-of-truth contract.
    """

    def _row(_user_id, _db):
        user = mfa_service.users_utils.get_user_by_id_or_404.return_value
        return getattr(user, "auth_mfa", None)

    with patch("auth.mfa.service.auth_mfa_crud.get_user_mfa_row", side_effect=_row):
        yield


# ---------------------------------------------------------------------------
# setup_user_mfa — reads mfa_enabled from auth_mfa
# ---------------------------------------------------------------------------


class TestSetupUserMFAReadSwitch:
    """setup_user_mfa reads mfa_enabled from auth_mfa, not users columns."""

    def test_raises_when_auth_mfa_enabled(self, mock_db):
        """
        Raises 400 when auth_mfa.mfa_enabled is True.
        """
        user = _make_user(mfa_enabled=True, mfa_secret="enc")

        with _patch_get_user(user), pytest.raises(HTTPException) as exc:
            mfa_service.setup_user_mfa(1, mock_db)

        assert exc.value.status_code == status.HTTP_400_BAD_REQUEST
        assert "already enabled" in exc.value.detail

    def test_proceeds_when_auth_mfa_disabled(self, mock_db):
        """
        Returns MFASetupResponse when auth_mfa.mfa_enabled is False.
        """
        user = _make_user(mfa_enabled=False)
        user.auth_mfa = MagicMock(spec=auth_mfa_models.UsersMFA)
        user.auth_mfa.mfa_enabled = False

        with _patch_get_user(user):
            result = mfa_service.setup_user_mfa(1, mock_db)

        assert result is not None

    def test_proceeds_when_auth_mfa_row_missing(self, mock_db):
        """
        Returns MFASetupResponse when auth_mfa is None
        (pre-migration edge case).
        """
        user = _make_user()
        user.auth_mfa = None

        with _patch_get_user(user):
            result = mfa_service.setup_user_mfa(1, mock_db)

        assert result is not None


# ---------------------------------------------------------------------------
# enable_user_mfa — reads mfa_enabled from auth_mfa
# ---------------------------------------------------------------------------


class TestEnableUserMFAReadSwitch:
    """enable_user_mfa reads mfa_enabled from auth_mfa."""

    def test_raises_when_auth_mfa_already_enabled(self, mock_db):
        """
        Raises 400 when auth_mfa says MFA is already on.
        """
        user = _make_user(mfa_enabled=True, mfa_secret="enc")

        with _patch_get_user(user), pytest.raises(HTTPException) as exc:
            mfa_service.enable_user_mfa(1, "secret", "123456", MagicMock(), mock_db)

        assert exc.value.status_code == status.HTTP_400_BAD_REQUEST
        assert "already enabled" in exc.value.detail


# ---------------------------------------------------------------------------
# disable_user_mfa — reads mfa_enabled from auth_mfa
# ---------------------------------------------------------------------------


class TestDisableUserMFAReadSwitch:
    """disable_user_mfa reads mfa_enabled from auth_mfa."""

    def test_raises_when_auth_mfa_not_enabled(self, mock_db):
        """
        Raises 400 when auth_mfa says MFA is off.
        """
        user = _make_user(mfa_enabled=False)

        with _patch_get_user(user), pytest.raises(HTTPException) as exc:
            mfa_service.disable_user_mfa(1, mock_db)

        assert exc.value.status_code == status.HTTP_400_BAD_REQUEST
        assert "not enabled" in exc.value.detail

    def test_raises_when_auth_mfa_row_missing(self, mock_db):
        """
        Raises 400 when auth_mfa is None (treated as disabled).
        """
        user = _make_user()
        user.auth_mfa = None

        with _patch_get_user(user), pytest.raises(HTTPException) as exc:
            mfa_service.disable_user_mfa(1, mock_db)

        assert exc.value.status_code == status.HTTP_400_BAD_REQUEST


# ---------------------------------------------------------------------------
# verify_user_mfa — reads mfa_enabled + mfa_secret from auth_mfa
# ---------------------------------------------------------------------------


class TestVerifyUserMFAReadSwitch:
    """verify_user_mfa reads both fields from auth_mfa."""

    def test_returns_false_when_auth_mfa_disabled(self, mock_db):
        """
        Returns False when auth_mfa.mfa_enabled is False,
        even if the legacy column was True.
        """
        user = _make_user(mfa_enabled=False)
        user.mfa_enabled = True  # legacy — must be ignored
        user.mfa_secret = "enc"  # legacy — must be ignored

        with _patch_get_user(user):
            result = mfa_service.verify_user_mfa(1, "123456", MagicMock(), mock_db)

        assert result is False

    def test_returns_false_when_auth_mfa_row_missing(self, mock_db):
        """Returns False when auth_mfa is None."""
        user = _make_user()
        user.auth_mfa = None
        user.mfa_enabled = True  # legacy True — must be ignored

        with _patch_get_user(user):
            result = mfa_service.verify_user_mfa(1, "123456", MagicMock(), mock_db)

        assert result is False

    def test_uses_auth_mfa_secret_for_totp(self, mock_db):
        """
        Decrypts the secret from auth_mfa.mfa_secret, not
        from the legacy users.mfa_secret column.
        """
        user = _make_user(mfa_enabled=True, mfa_secret="auth_enc_secret")
        user.mfa_secret = "WRONG_legacy_secret"  # must be ignored

        with (
            _patch_get_user(user),
            patch(
                "auth.mfa.service.core_cryptography.decrypt_token_fernet",
                return_value=None,  # decrypt fails → returns False cleanly
            ) as mock_decrypt,
        ):
            mfa_service.verify_user_mfa(1, "123456", MagicMock(), mock_db)

        mock_decrypt.assert_called_once_with("auth_enc_secret")


# ---------------------------------------------------------------------------
# is_mfa_enabled_for_user — reads from auth_mfa
# ---------------------------------------------------------------------------


class TestIsMFAEnabledForUserReadSwitch:
    """is_mfa_enabled_for_user reads from auth_mfa."""

    @pytest.fixture(autouse=True)
    def _wire_mfa_row(self):
        """Mirror auth_mfa_crud.get_user_mfa_row to the mocked user's auth_mfa.

        Production reads the ``users_mfa`` row via
        ``auth_mfa_crud.get_user_mfa_row``; resolve it from the patched
        user mock so the read still derives from ``auth_mfa``.
        """

        def _row(_user_id, _db):
            user = mfa_service.users_utils.get_user_by_id_or_404.return_value
            return getattr(user, "auth_mfa", None)

        with patch("auth.mfa.service.auth_mfa_crud.get_user_mfa_row", side_effect=_row):
            yield

    def test_returns_true_when_auth_mfa_enabled_with_secret(self, mock_db):
        """
        Returns True only when auth_mfa row is enabled AND has a secret.
        """
        user = _make_user(mfa_enabled=True, mfa_secret="enc")
        # Legacy columns deliberately wrong
        user.mfa_enabled = False
        user.mfa_secret = None

        with _patch_get_user(user):
            result = mfa_service.is_mfa_enabled_for_user(1, mock_db)

        assert result is True

    def test_returns_false_when_auth_mfa_enabled_no_secret(self, mock_db):
        """Returns False when mfa_enabled but secret is None."""
        user = _make_user(mfa_enabled=True, mfa_secret=None)

        with _patch_get_user(user):
            result = mfa_service.is_mfa_enabled_for_user(1, mock_db)

        assert result is False

    def test_returns_false_when_auth_mfa_row_missing(self, mock_db):
        """Returns False when auth_mfa is None."""
        user = _make_user()
        user.auth_mfa = None
        user.mfa_enabled = True  # legacy True — must be ignored
        user.mfa_secret = "enc"  # legacy — must be ignored

        with _patch_get_user(user):
            result = mfa_service.is_mfa_enabled_for_user(1, mock_db)

        assert result is False

    def test_returns_false_when_user_not_found(self, mock_db):
        """Returns False when user does not exist."""
        with patch(
            "auth.mfa.service.users_utils.get_user_by_id_or_404",
            side_effect=HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found",
            ),
        ):
            result = mfa_service.is_mfa_enabled_for_user(99, mock_db)

        assert result is False
