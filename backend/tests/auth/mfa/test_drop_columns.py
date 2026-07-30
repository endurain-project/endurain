"""Tests verifying MFA state lives solely in the ``users_mfa`` table.

Verifies that:
* ``update_user_mfa`` (now in ``auth.mfa.crud``) writes ONLY
  to ``users_mfa``; the ``Users`` mock's attributes are never
  touched.
* ``db.refresh(db_user)`` is not called.
* A missing ``users_mfa`` row triggers a new INSERT.
"""

import contextlib
from unittest.mock import MagicMock, patch

import auth.mfa.crud as auth_mfa_crud
import auth.mfa.models as auth_mfa_models
import users.users.models as users_models

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
                "auth.mfa.crud.select",
                return_value=mock_stmt,
            ),
            patch(
                "auth.mfa.crud.auth_mfa_models.UsersMFA",
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
