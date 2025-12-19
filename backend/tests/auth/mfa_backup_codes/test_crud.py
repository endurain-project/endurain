"""Tests for MFA backup codes CRUD operations."""

import pytest
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch
from fastapi import HTTPException, status

import auth.mfa_backup_codes.crud as backup_crud
import auth.mfa_backup_codes.models as backup_models


class TestGetUserBackupCodes:
    """Test suite for get_user_backup_codes function."""

    def test_get_user_backup_codes_success(self, mock_db):
        """Test successful retrieval of user backup codes."""
        # Arrange
        user_id = 1
        mock_code1 = MagicMock(spec=backup_models.MFABackupCode)
        mock_code2 = MagicMock(spec=backup_models.MFABackupCode)

        mock_query = mock_db.query.return_value
        mock_filter = mock_query.filter.return_value
        mock_filter.all.return_value = [mock_code1, mock_code2]

        # Act
        result = backup_crud.get_user_backup_codes(user_id, mock_db)

        # Assert
        assert result == [mock_code1, mock_code2]
        mock_db.query.assert_called_once_with(backup_models.MFABackupCode)

    def test_get_user_backup_codes_exception(self, mock_db):
        """Test exception handling in get_user_backup_codes."""
        # Arrange
        user_id = 1
        mock_db.query.side_effect = Exception("Database error")

        # Act & Assert
        with pytest.raises(HTTPException) as exc_info:
            backup_crud.get_user_backup_codes(user_id, mock_db)

        assert exc_info.value.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
        assert exc_info.value.detail == "Failed to retrieve backup codes"


class TestGetUserUnusedBackupCodes:
    """Test suite for get_user_unused_backup_codes function."""

    def test_get_unused_codes_success(self, mock_db):
        """Test successful retrieval of unused backup codes."""
        # Arrange
        user_id = 1
        mock_code1 = MagicMock(spec=backup_models.MFABackupCode, used=False)
        mock_code2 = MagicMock(spec=backup_models.MFABackupCode, used=False)

        mock_query = mock_db.query.return_value
        mock_filter = mock_query.filter.return_value
        mock_filter.all.return_value = [mock_code1, mock_code2]

        # Act
        result = backup_crud.get_user_unused_backup_codes(user_id, mock_db)

        # Assert
        assert result == [mock_code1, mock_code2]
        assert all(not code.used for code in result)

    def test_get_unused_codes_exception(self, mock_db):
        """Test exception handling in get_user_unused_backup_codes."""
        # Arrange
        user_id = 1
        mock_db.query.side_effect = Exception("Database error")

        # Act & Assert
        with pytest.raises(HTTPException) as exc_info:
            backup_crud.get_user_unused_backup_codes(user_id, mock_db)

        assert exc_info.value.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR


class TestCreateBackupCodes:
    """Test suite for create_backup_codes function."""

    def test_create_backup_codes_success(self, mock_db, password_hasher):
        """Test successful backup codes creation."""
        # Arrange
        user_id = 1
        count = 10

        # Mock the model instantiation to avoid SQLAlchemy mapper issues
        with patch.object(backup_crud, "delete_user_backup_codes"), patch(
            "auth.mfa_backup_codes.crud.mfa_backup_codes_models.MFABackupCode"
        ):
            # Act
            codes = backup_crud.create_backup_codes(
                user_id, password_hasher, mock_db, count
            )

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
        with patch.object(
            backup_crud, "delete_user_backup_codes"
        ) as mock_delete, patch(
            "auth.mfa_backup_codes.crud.mfa_backup_codes_models.MFABackupCode"
        ):
            # Act
            backup_crud.create_backup_codes(user_id, password_hasher, mock_db)

            # Assert
            mock_delete.assert_called_once_with(user_id, mock_db)

    def test_create_backup_codes_custom_count(self, mock_db, password_hasher):
        """Test creation with custom code count."""
        # Arrange
        user_id = 1
        custom_count = 5

        # Mock the model instantiation to avoid SQLAlchemy mapper issues
        with patch.object(backup_crud, "delete_user_backup_codes"), patch(
            "auth.mfa_backup_codes.crud.mfa_backup_codes_models.MFABackupCode"
        ):
            # Act
            codes = backup_crud.create_backup_codes(
                user_id, password_hasher, mock_db, custom_count
            )

            # Assert
            assert len(codes) == custom_count

    def test_create_backup_codes_exception(self, mock_db, password_hasher):
        """Test exception handling in create_backup_codes."""
        # Arrange
        user_id = 1
        mock_db.add.side_effect = Exception("Database error")

        with patch.object(backup_crud, "delete_user_backup_codes"):
            # Act & Assert
            with pytest.raises(HTTPException) as exc_info:
                backup_crud.create_backup_codes(user_id, password_hasher, mock_db)

            assert exc_info.value.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR


class TestMarkBackupCodeAsUsed:
    """Test suite for mark_backup_code_as_used function."""

    def test_mark_code_as_used_success(self, mock_db):
        """Test successful marking of backup code as used."""
        # Arrange
        user_id = 1
        code_hash = "hashed_code"

        mock_code = MagicMock(spec=backup_models.MFABackupCode)
        mock_code.used = False
        mock_code.used_at = None

        mock_query = mock_db.query.return_value
        mock_filter = mock_query.filter.return_value
        mock_filter.first.return_value = mock_code

        # Act
        backup_crud.mark_backup_code_as_used(code_hash, user_id, mock_db)

        # Assert
        assert mock_code.used is True
        assert mock_code.used_at is not None
        mock_db.commit.assert_called_once()
        mock_db.refresh.assert_called_once_with(mock_code)

    def test_mark_code_as_used_not_found(self, mock_db):
        """Test marking non-existent code doesn't raise exception."""
        # Arrange
        user_id = 1
        code_hash = "nonexistent_hash"

        mock_query = mock_db.query.return_value
        mock_filter = mock_query.filter.return_value
        mock_filter.first.return_value = None

        # Act (should not raise exception)
        backup_crud.mark_backup_code_as_used(code_hash, user_id, mock_db)

        # Assert
        mock_db.commit.assert_not_called()

    def test_mark_code_as_used_exception(self, mock_db):
        """Test exception handling in mark_backup_code_as_used."""
        # Arrange
        user_id = 1
        code_hash = "hashed_code"
        mock_db.query.side_effect = Exception("Database error")

        # Act & Assert
        with pytest.raises(HTTPException) as exc_info:
            backup_crud.mark_backup_code_as_used(code_hash, user_id, mock_db)

        assert exc_info.value.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
        mock_db.rollback.assert_called_once()


class TestDeleteUserBackupCodes:
    """Test suite for delete_user_backup_codes function."""

    def test_delete_codes_success(self, mock_db):
        """Test successful deletion of user backup codes."""
        # Arrange
        user_id = 1
        expected_count = 10

        mock_query = mock_db.query.return_value
        mock_filter = mock_query.filter.return_value
        mock_filter.delete.return_value = expected_count

        # Act
        result = backup_crud.delete_user_backup_codes(user_id, mock_db)

        # Assert
        assert result == expected_count
        mock_db.commit.assert_called_once()

    def test_delete_codes_none_found(self, mock_db):
        """Test deletion when no codes exist."""
        # Arrange
        user_id = 1

        mock_query = mock_db.query.return_value
        mock_filter = mock_query.filter.return_value
        mock_filter.delete.return_value = 0

        # Act
        result = backup_crud.delete_user_backup_codes(user_id, mock_db)

        # Assert
        assert result == 0
        mock_db.commit.assert_called_once()

    def test_delete_codes_exception(self, mock_db):
        """Test exception handling in delete_user_backup_codes."""
        # Arrange
        user_id = 1
        mock_db.query.side_effect = Exception("Database error")

        # Act & Assert
        with pytest.raises(HTTPException) as exc_info:
            backup_crud.delete_user_backup_codes(user_id, mock_db)

        assert exc_info.value.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
        mock_db.rollback.assert_called_once()
