"""Tests for ``modules.auth.credentials.crud``."""

from unittest.mock import MagicMock, patch

import modules.auth.credentials.crud as auth_credentials_crud
import modules.auth.credentials.models as auth_credentials_models


class TestGetCredential:
    """``get_credential`` returns the user's credential row or ``None``."""

    def test_returns_existing_row(self):
        db = MagicMock()
        fake_row = MagicMock(spec=auth_credentials_models.LocalCredential)
        db.execute.return_value.scalar_one_or_none.return_value = fake_row

        result = auth_credentials_crud.get_credential(42, db)

        assert result is fake_row
        db.execute.assert_called_once()

    def test_returns_none_when_absent(self):
        db = MagicMock()
        db.execute.return_value.scalar_one_or_none.return_value = None

        result = auth_credentials_crud.get_credential(42, db)

        assert result is None


class TestUpsertPasswordHash:
    """``upsert_password_hash`` inserts when absent, updates when present."""

    def test_inserts_when_absent(self):
        db = MagicMock()
        db.execute.return_value.scalar_one_or_none.return_value = None
        fake_row = MagicMock(spec=auth_credentials_models.LocalCredential)

        with (
            patch("modules.auth.credentials.crud.select", return_value=MagicMock()),
            patch(
                "modules.auth.credentials.crud.auth_credentials_models.LocalCredential",
                return_value=fake_row,
            ) as ctor,
        ):
            auth_credentials_crud.upsert_password_hash(7, "hash-value", db)

        ctor.assert_called_once_with(user_id=7, password_hash="hash-value")
        db.add.assert_called_once_with(fake_row)
        db.commit.assert_called_once()

    def test_updates_when_present(self):
        db = MagicMock()
        existing = MagicMock(spec=auth_credentials_models.LocalCredential)
        db.execute.return_value.scalar_one_or_none.return_value = existing

        auth_credentials_crud.upsert_password_hash(7, "new-hash", db)

        assert existing.password_hash == "new-hash"
        db.add.assert_not_called()
        db.commit.assert_called_once()


class TestDeleteCredential:
    """``delete_credential`` removes the user's credential row."""

    def test_executes_delete_and_commits(self):
        db = MagicMock()

        auth_credentials_crud.delete_credential(7, db)

        db.execute.assert_called_once()
        db.commit.assert_called_once()
