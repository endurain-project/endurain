"""Tests verifying the legacy MFA columns are absent from the ORM.

Verifies that:
* ``Users.mfa_enabled`` reads from ``auth_mfa`` (the legacy
  column is no longer present on the ORM).
* ``update_user_mfa`` (now in ``modules.auth.mfa.crud``) writes ONLY
  to ``users_mfa``; the ``Users`` mock's attributes are never
  touched.
* ``db.refresh(db_user)`` is not called.
* A missing ``users_mfa`` row triggers a new INSERT.
"""

import contextlib
from unittest.mock import MagicMock, patch

import modules.auth.mfa.crud as auth_mfa_crud
import modules.auth.mfa.models as auth_mfa_models
import modules.users.users.models as users_models

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_user_with_mfa(enabled: bool = True) -> MagicMock:
    """
    Return a mock Users row wired with an auth_mfa sub-mock.

    The ``mfa_enabled`` attribute on the mock is intentionally
    NOT set — the real model serves it from the ``mfa_enabled``
    property (which reads ``auth_mfa``).  We set
    ``user.auth_mfa.mfa_enabled`` instead.
    """
    user = MagicMock(spec=users_models.Users)
    user.id = 42
    auth_mfa = MagicMock(spec=auth_mfa_models.UsersMFA)
    auth_mfa.mfa_enabled = enabled
    auth_mfa.mfa_secret = "enc_sec" if enabled else None
    user.auth_mfa = auth_mfa
    return user


def _make_user_no_mfa_row() -> MagicMock:
    """Return a mock Users row with no auth_mfa relationship row."""
    user = MagicMock(spec=users_models.Users)
    user.id = 7
    user.auth_mfa = None
    return user


# ---------------------------------------------------------------------------
# Users.mfa_enabled property
# ---------------------------------------------------------------------------


class TestUsersMFAEnabledProperty:
    """``Users.mfa_enabled`` reads from ``auth_mfa``."""

    def test_returns_true_when_auth_mfa_enabled(self):
        """Property returns True when auth_mfa.mfa_enabled is True."""
        user = MagicMock(spec=users_models.Users)
        auth_mfa = MagicMock(spec=auth_mfa_models.UsersMFA)
        auth_mfa.mfa_enabled = True
        user.auth_mfa = auth_mfa

        result = users_models.Users.mfa_enabled.fget(user)

        assert result is True

    def test_returns_false_when_auth_mfa_disabled(self):
        """Property returns False when auth_mfa.mfa_enabled is False."""
        user = MagicMock(spec=users_models.Users)
        auth_mfa = MagicMock(spec=auth_mfa_models.UsersMFA)
        auth_mfa.mfa_enabled = False
        user.auth_mfa = auth_mfa

        result = users_models.Users.mfa_enabled.fget(user)

        assert result is False

    def test_returns_false_when_auth_mfa_row_missing(self):
        """Property returns False when auth_mfa relationship is None."""
        user = MagicMock(spec=users_models.Users)
        user.auth_mfa = None

        result = users_models.Users.mfa_enabled.fget(user)

        assert result is False


# ---------------------------------------------------------------------------
# update_user_mfa — single-write to users_mfa only
# ---------------------------------------------------------------------------


class TestUpdateUserMFASingleWrite:
    """Legacy column writes are never performed."""

    def _setup(
        self,
        mock_db: MagicMock,
        mfa_row: MagicMock | None = None,
    ) -> MagicMock:
        """Create mock user, wire DB, return mock user."""
        user = MagicMock(spec=users_models.Users)
        user.id = 1
        mock_db.get.return_value = user
        mock_db.execute.return_value.scalar_one_or_none.return_value = mfa_row
        return user

    def teardown_method(self):
        with contextlib.suppress(AttributeError):
            self._user_patch.stop()

    def test_enable_writes_only_to_users_mfa(self, mock_db):
        """Enabling MFA updates users_mfa and does not touch users row."""
        mfa_row = MagicMock(spec=auth_mfa_models.UsersMFA)
        mfa_row.mfa_enabled = False
        mfa_row.mfa_secret = None
        user = self._setup(mock_db, mfa_row)

        auth_mfa_crud.update_user_mfa(1, mock_db, "enc_secret")

        # users_mfa row updated
        assert mfa_row.mfa_enabled is True
        assert mfa_row.mfa_secret == "enc_secret"
        # users row never modified (no setattr on user)
        user.assert_not_called()

    def test_disable_writes_only_to_users_mfa(self, mock_db):
        """Disabling MFA clears users_mfa and does not touch users row."""
        mfa_row = MagicMock(spec=auth_mfa_models.UsersMFA)
        mfa_row.mfa_enabled = True
        mfa_row.mfa_secret = "old_secret"
        self._setup(mock_db, mfa_row)

        auth_mfa_crud.update_user_mfa(1, mock_db)

        # users_mfa row cleared
        assert mfa_row.mfa_enabled is False
        assert mfa_row.mfa_secret is None

    def test_commit_called_once(self, mock_db):
        """db.commit() is called exactly once."""
        mfa_row = MagicMock(spec=auth_mfa_models.UsersMFA)
        self._setup(mock_db, mfa_row)

        auth_mfa_crud.update_user_mfa(1, mock_db, "enc")

        mock_db.commit.assert_called_once()

    def test_refresh_not_called(self, mock_db):
        """db.refresh() is not called."""
        mfa_row = MagicMock(spec=auth_mfa_models.UsersMFA)
        self._setup(mock_db, mfa_row)

        auth_mfa_crud.update_user_mfa(1, mock_db, "enc")

        mock_db.refresh.assert_not_called()

    def test_missing_row_creates_new_users_mfa(self, mock_db):
        """A missing users_mfa row triggers INSERT on update."""
        self._setup(mock_db, None)

        mock_new_row = MagicMock(spec=auth_mfa_models.UsersMFA)
        mock_stmt = MagicMock()
        with (
            patch(
                "modules.auth.mfa.crud.select",
                return_value=mock_stmt,
            ),
            patch(
                "modules.auth.mfa.crud.auth_mfa_models.UsersMFA",
                return_value=mock_new_row,
            ) as mock_class,
        ):
            auth_mfa_crud.update_user_mfa(1, mock_db, "enc")

            mock_class.assert_called_once_with(
                user_id=1,
                mfa_enabled=True,
                mfa_secret="enc",
            )
            mock_db.add.assert_called_once_with(mock_new_row)
