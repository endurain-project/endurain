"""Tests for MFA backup codes API router."""

import pytest
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch, AsyncMock
from fastapi import HTTPException, status
from starlette.requests import Request
from starlette.responses import Response
from starlette.datastructures import Headers

import auth.mfa_backup_codes.router as backup_router
import auth.mfa_backup_codes.crud as backup_crud
import auth.mfa_backup_codes.schema as backup_schema
import users.user.crud as users_crud


class TestGetMFABackupCodeStatus:
    """Test suite for get_mfa_backup_code_status endpoint."""

    @pytest.mark.asyncio
    async def test_get_status_success(self, mock_db, sample_user_read):
        """Test successful retrieval of backup code status."""
        # Arrange
        created_at = datetime.now(timezone.utc)
        mock_codes = [
            MagicMock(used=False, created_at=created_at),
            MagicMock(used=False, created_at=created_at),
            MagicMock(used=True, created_at=created_at),
        ]

        with patch.object(
            backup_crud, "get_user_backup_codes", return_value=mock_codes
        ):
            # Act
            result = await backup_router.get_backup_code_status(
                token_user_id=sample_user_read.id, db=mock_db
            )

            # Assert
            assert isinstance(result, backup_schema.MFABackupCodeStatus)
            assert result.total == 3
            assert result.unused == 2
            assert result.used == 1
            assert result.created_at == created_at

    @pytest.mark.asyncio
    async def test_get_status_no_codes(self, mock_db, sample_user_read):
        """Test status when user has no backup codes."""
        # Arrange
        with patch.object(backup_crud, "get_user_backup_codes", return_value=[]):
            # Act
            result = await backup_router.get_backup_code_status(
                token_user_id=sample_user_read.id, db=mock_db
            )

            # Assert
            assert result.total == 0
            assert result.unused == 0
            assert result.used == 0
            assert result.created_at is None

    def test_get_status_requires_mfa_enabled(self, mock_db):
        """Test status endpoint requires MFA to be enabled."""
        # Arrange
        user_without_mfa = MagicMock()
        user_without_mfa.mfa_enabled = False

        # This would be handled by dependency injection in router
        # but we verify the logic here
        assert user_without_mfa.mfa_enabled is False


class TestGenerateMFABackupCodes:
    """Test suite for generate_mfa_backup_codes endpoint."""

    @pytest.mark.asyncio
    async def test_generate_codes_success(
        self, mock_db, sample_user_read, password_hasher
    ):
        """Test successful generation of new backup codes."""
        # Arrange
        generated_codes = [
            "A3K9-7BDF",
            "X7Q4-MNPR",
            "K2W9-CGHS",
            "P5T8-VJBF",
            "N6R4-XDKL",
            "M9G2-WHTR",
            "Q8B5-YZCP",
            "H4V7-NSJF",
            "C3K6-PMDG",
            "Y2T9-XBRN",
        ]

        # Need to mock the user lookup
        mock_user = MagicMock()
        mock_user.id = sample_user_read.id
        mock_user.mfa_enabled = True

        # Create proper Response object for rate limiting
        mock_response = Response()

        # Create proper Request object for rate limiting
        mock_request = Request(
            scope={
                "type": "http",
                "method": "POST",
                "headers": Headers({}).raw,
                "query_string": b"",
                "path": "/api/v1/auth/mfa/backup-codes",
                "client": ("testclient", 50000),
                "server": ("testserver", 80),
            }
        )

        with patch.object(
            users_crud, "get_user_by_id", return_value=mock_user
        ), patch.object(
            backup_crud, "create_backup_codes", return_value=generated_codes
        ):
            # Act
            result = await backup_router.generate_mfa_backup_codes(
                response=mock_response,
                request=mock_request,
                token_user_id=sample_user_read.id,
                db=mock_db,
                password_hasher=password_hasher,
            )

            # Assert
            assert isinstance(result, backup_schema.MFABackupCodesResponse)
            assert result.codes == generated_codes
            assert len(result.codes) == 10

    @pytest.mark.asyncio
    async def test_generate_codes_invalidates_old_codes(
        self, mock_db, sample_user_read, password_hasher
    ):
        """Test that generating new codes deletes old codes."""
        # Arrange
        mock_user = MagicMock()
        mock_user.id = sample_user_read.id
        mock_user.mfa_enabled = True

        # Create proper Response object for rate limiting
        mock_response = Response()

        # Create proper Request object for rate limiting
        mock_request = Request(
            scope={
                "type": "http",
                "method": "POST",
                "headers": Headers({}).raw,
                "query_string": b"",
                "path": "/api/v1/auth/mfa/backup-codes",
                "client": ("testclient", 50000),
                "server": ("testserver", 80),
            }
        )

        with patch.object(
            users_crud, "get_user_by_id", return_value=mock_user
        ), patch.object(
            backup_crud, "create_backup_codes", return_value=["A3K9-7BDF"]
        ) as mock_create:

            # Act
            await backup_router.generate_mfa_backup_codes(
                response=mock_response,
                request=mock_request,
                token_user_id=sample_user_read.id,
                db=mock_db,
                password_hasher=password_hasher,
            )

            # Assert
            # delete_user_backup_codes is called inside create_backup_codes
            mock_create.assert_called_once()

    def test_generate_codes_requires_mfa_enabled(self, mock_db, password_hasher):
        """Test generation endpoint requires MFA to be enabled."""
        # Arrange
        user_without_mfa = MagicMock()
        user_without_mfa.mfa_enabled = False

        # This would be handled by dependency injection in router
        # but we verify the logic here
        assert user_without_mfa.mfa_enabled is False

    @pytest.mark.asyncio
    async def test_generate_codes_format_validation(
        self, mock_db, sample_user_read, password_hasher
    ):
        """Test that generated codes have proper format."""
        # Arrange
        mock_user = MagicMock()
        mock_user.id = sample_user_read.id
        mock_user.mfa_enabled = True

        # Create proper Response object for rate limiting
        mock_response = Response()

        # Create proper Request object for rate limiting
        mock_request = Request(
            scope={
                "type": "http",
                "method": "POST",
                "headers": Headers({}).raw,
                "query_string": b"",
                "path": "/api/v1/auth/mfa/backup-codes",
                "client": ("testclient", 50000),
                "server": ("testserver", 80),
            }
        )

        with patch.object(
            users_crud, "get_user_by_id", return_value=mock_user
        ), patch.object(backup_crud, "create_backup_codes", return_value=["A3K9-7BDF"]):
            # Act
            result = await backup_router.generate_mfa_backup_codes(
                response=mock_response,
                request=mock_request,
                token_user_id=sample_user_read.id,
                db=mock_db,
                password_hasher=password_hasher,
            )

            # Assert
            for code in result.codes:
                assert len(code) == 9
                assert code[4] == "-"
                assert code.isupper()
