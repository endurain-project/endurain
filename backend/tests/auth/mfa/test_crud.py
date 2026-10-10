"""Tests for ``modules.auth.mfa.crud.create_users_mfa_row``."""

from unittest.mock import MagicMock, patch

import modules.auth.mfa.crud as auth_mfa_crud
import modules.auth.mfa.models as auth_mfa_models


class TestCreateUsersMFARow:
    """``create_users_mfa_row`` persists a disabled row for a user."""

    def test_creates_disabled_row(self):
        db = MagicMock()
        fake_row = MagicMock(spec=auth_mfa_models.UsersMFA)

        with patch.object(
            auth_mfa_crud.auth_mfa_models,
            "UsersMFA",
            return_value=fake_row,
        ) as ctor:
            row = auth_mfa_crud.create_users_mfa_row(42, db)

        ctor.assert_called_once_with(user_id=42, mfa_enabled=False, mfa_secret=None)
        assert row is fake_row

    def test_persists_via_db(self):
        db = MagicMock()
        fake_row = MagicMock(spec=auth_mfa_models.UsersMFA)

        with patch.object(
            auth_mfa_crud.auth_mfa_models,
            "UsersMFA",
            return_value=fake_row,
        ):
            row = auth_mfa_crud.create_users_mfa_row(7, db)

        db.add.assert_called_once_with(row)
        db.commit.assert_called_once()
        db.refresh.assert_called_once_with(row)
