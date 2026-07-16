"""Tests for MFA backup codes CRUD operations."""

from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException, status
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.sql import operators

import modules.auth.mfa.backup_codes.crud as backup_crud
import modules.auth.mfa.backup_codes.models as backup_models


class TestGetUserBackupCodes:
    """Test suite for get_user_backup_codes function."""

    def test_get_user_backup_codes_success(self, mock_db):
        """Test successful retrieval of user backup codes."""
        # Arrange
        user_id = 1
        mock_code1 = MagicMock(spec=backup_models.MFABackupCode)
        mock_code2 = MagicMock(spec=backup_models.MFABackupCode)

        mock_db.execute.return_value.scalars.return_value.all.return_value = [
            mock_code1,
            mock_code2,
        ]

        # Act
        result = backup_crud.get_user_backup_codes(user_id, mock_db)

        # Assert
        assert result == [mock_code1, mock_code2]
        mock_db.execute.assert_called_once()

    def test_get_user_backup_codes_exception(self, mock_db):
        """Test exception handling in get_user_backup_codes."""
        # Arrange
        user_id = 1
        mock_db.execute.side_effect = SQLAlchemyError("Database error")

        # Act & Assert
        with pytest.raises(HTTPException) as exc_info:
            backup_crud.get_user_backup_codes(user_id, mock_db)

        assert exc_info.value.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
        assert "Database error" in exc_info.value.detail


class TestGetUserUnusedBackupCodes:
    """Test suite for get_user_unused_backup_codes function."""

    def test_get_unused_codes_success(self, mock_db):
        """Test successful retrieval of unused backup codes."""
        # Arrange
        user_id = 1
        mock_code1 = MagicMock(spec=backup_models.MFABackupCode, used=False)
        mock_code2 = MagicMock(spec=backup_models.MFABackupCode, used=False)

        mock_scalars = mock_db.execute.return_value.scalars.return_value
        mock_scalars.all.return_value = [mock_code1, mock_code2]

        # Act
        result = backup_crud.get_user_unused_backup_codes(user_id, mock_db)

        # Assert
        assert result == [mock_code1, mock_code2]
        assert all(not code.used for code in result)

    def test_get_unused_codes_exception(self, mock_db):
        """Test exception handling in get_user_unused_backup_codes."""
        # Arrange
        user_id = 1
        mock_db.execute.side_effect = SQLAlchemyError("Database error")

        # Act & Assert
        with pytest.raises(HTTPException) as exc_info:
            backup_crud.get_user_unused_backup_codes(user_id, mock_db)

        assert exc_info.value.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR

    def test_get_unused_codes_excludes_expired_codes(self, mock_db):
        """Test unused backup code lookup enforces expires_at."""
        # Arrange
        user_id = 1
        mock_db.execute.return_value.scalars.return_value.all.return_value = []

        # Act
        backup_crud.get_user_unused_backup_codes(user_id, mock_db)

        # Assert
        stmt = mock_db.execute.call_args.args[0]
        expiry_clause = stmt._where_criteria[2]
        expiry_checks = list(expiry_clause.clauses)
        assert any(check.left.name == "expires_at" and check.operator is operators.is_ for check in expiry_checks)
        assert any(check.left.name == "expires_at" and check.operator is operators.gt for check in expiry_checks)


class TestCreateBackupCodes:
    """Test suite for create_backup_codes function."""

    def test_create_backup_codes_success(self, mock_db, password_hasher):
        """Test successful backup codes creation."""
        # Arrange
        user_id = 1
        count = 10

        # Mock the model instantiation to avoid SQLAlchemy mapper issues
        with (
            patch("modules.auth.mfa.backup_codes.crud.delete") as mock_sa_delete,
            patch("modules.auth.mfa.backup_codes.crud.mfa_backup_codes_models.MFABackupCode"),
        ):
            mock_sa_delete.return_value.where.return_value = MagicMock()
            # Act
            codes = backup_crud.create_backup_codes(user_id, password_hasher, mock_db, count)

            # Assert
            assert len(codes) == count
            assert all(len(code) == 9 for code in codes)  # XXXX-XXXX format
            assert all("-" in code for code in codes)
            mock_db.commit.assert_called_once()

    def test_create_backup_codes_deletes_old_codes(self, mock_db, password_hasher):
        """Test that old codes are deleted before creating new ones."""
        # Arrange
        user_id = 1

        # Mock the model instantiation to avoid SQLAlchemy mapper issues
        with (
            patch("modules.auth.mfa.backup_codes.crud.delete") as mock_sa_delete,
            patch("modules.auth.mfa.backup_codes.crud.mfa_backup_codes_models.MFABackupCode"),
        ):
            mock_sa_delete.return_value.where.return_value = MagicMock()
            # Act
            backup_crud.create_backup_codes(user_id, password_hasher, mock_db)

            # Assert
            mock_sa_delete.assert_called_once()
            mock_db.execute.assert_called()

    def test_create_backup_codes_custom_count(self, mock_db, password_hasher):
        """Test creation with custom code count."""
        # Arrange
        user_id = 1
        custom_count = 5

        # Mock the model instantiation to avoid SQLAlchemy mapper issues
        with (
            patch("modules.auth.mfa.backup_codes.crud.delete") as mock_sa_delete,
            patch("modules.auth.mfa.backup_codes.crud.mfa_backup_codes_models.MFABackupCode"),
        ):
            mock_sa_delete.return_value.where.return_value = MagicMock()
            # Act
            codes = backup_crud.create_backup_codes(user_id, password_hasher, mock_db, custom_count)

            # Assert
            assert len(codes) == custom_count

    def test_create_backup_codes_exception(self, mock_db, password_hasher):
        """Test exception handling in create_backup_codes."""
        # Arrange
        user_id = 1
        mock_db.commit.side_effect = SQLAlchemyError("Database error")

        # Mock the model instantiation to avoid SQLAlchemy mapper issues
        with (
            patch("modules.auth.mfa.backup_codes.crud.delete") as mock_sa_delete,
            patch("modules.auth.mfa.backup_codes.crud.mfa_backup_codes_models.MFABackupCode"),
        ):
            mock_sa_delete.return_value.where.return_value = MagicMock()
            # Act & Assert
            with pytest.raises(HTTPException) as exc_info:
                backup_crud.create_backup_codes(user_id, password_hasher, mock_db)

            assert exc_info.value.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
            assert "Database error" in exc_info.value.detail

    def test_create_backup_codes_http_exception_reraise(self, mock_db, password_hasher):
        """Test that HTTPException from delete is re-raised."""
        # Arrange
        user_id = 1
        http_exc = HTTPException(status_code=404, detail="User not found")

        # Use db.execute to trigger HTTPException re-raise path
        with (
            patch("modules.auth.mfa.backup_codes.crud.delete") as mock_sa_delete,
            patch("modules.auth.mfa.backup_codes.crud.mfa_backup_codes_models.MFABackupCode"),
        ):
            mock_sa_delete.return_value.where.return_value = MagicMock()
            mock_db.execute.side_effect = http_exc

            # Act & Assert
            with pytest.raises(HTTPException) as exc_info:
                backup_crud.create_backup_codes(user_id, password_hasher, mock_db)

            # Should re-raise the same HTTPException
            assert exc_info.value.status_code == 404
            assert exc_info.value.detail == "User not found"


class TestMarkBackupCodeAsUsed:
    """Test suite for mark_backup_code_as_used function."""

    def test_mark_code_as_used_success(self, mock_db):
        """Test successful marking of backup code as used."""
        # Arrange
        user_id = 1
        code_id = 42

        mock_code = MagicMock(spec=backup_models.MFABackupCode)
        mock_code.used = False
        mock_code.user_id = user_id

        mock_db.get.return_value = mock_code

        # Act
        backup_crud.mark_backup_code_as_used(code_id, user_id, mock_db)

        # Assert
        mock_db.commit.assert_called_once()
        mock_db.refresh.assert_called_once_with(mock_code)

    def test_mark_code_as_used_not_found(self, mock_db):
        """Test marking non-existent code raises 404."""
        # Arrange
        user_id = 1
        code_id = 99

        mock_db.get.return_value = None

        # Act & Assert
        with pytest.raises(HTTPException) as exc_info:
            backup_crud.mark_backup_code_as_used(code_id, user_id, mock_db)

        assert exc_info.value.status_code == status.HTTP_404_NOT_FOUND

    def test_mark_code_as_used_exception(self, mock_db):
        """Test exception handling in mark_backup_code_as_used."""
        # Arrange
        user_id = 1
        code_id = 42
        mock_db.get.side_effect = SQLAlchemyError("Database error")

        # Act & Assert
        with pytest.raises(HTTPException) as exc_info:
            backup_crud.mark_backup_code_as_used(code_id, user_id, mock_db)

        assert exc_info.value.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR


class TestDeleteUserBackupCodes:
    """Test suite for delete_user_backup_codes function."""

    def test_delete_codes_success(self, mock_db):
        """Test successful deletion of user backup codes."""
        # Arrange
        user_id = 1
        expected_count = 10

        mock_db.execute.return_value.rowcount = expected_count

        # Act
        result = backup_crud.delete_user_backup_codes(user_id, mock_db)

        # Assert
        assert result == expected_count
        mock_db.commit.assert_called_once()

    def test_delete_codes_none_found(self, mock_db):
        """Test deletion when no codes exist."""
        # Arrange
        user_id = 1

        mock_db.execute.return_value.rowcount = 0

        # Act
        result = backup_crud.delete_user_backup_codes(user_id, mock_db)

        # Assert
        assert result == 0
        mock_db.commit.assert_called_once()

    def test_delete_codes_exception(self, mock_db):
        """Test exception handling in delete_user_backup_codes."""
        # Arrange
        user_id = 1
        mock_db.execute.side_effect = SQLAlchemyError("Database error")

        # Act & Assert
        with pytest.raises(HTTPException) as exc_info:
            backup_crud.delete_user_backup_codes(user_id, mock_db)

        assert exc_info.value.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
