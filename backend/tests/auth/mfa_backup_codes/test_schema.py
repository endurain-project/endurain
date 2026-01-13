"""
Tests for auth.mfa_backup_codes.schema module.

This module tests Pydantic schemas for MFA backup codes.
"""

import pytest
from datetime import datetime, timezone
from pydantic import ValidationError

import auth.mfa_backup_codes.schema as mfa_schema


class TestMFABackupCodesResponse:
    """Tests for MFABackupCodesResponse Pydantic model."""

    def test_valid_backup_codes_response(self):
        """Test valid backup codes response."""
        now = datetime.now(timezone.utc)
        codes = ["ABC123XYZ", "DEF456UVW", "GHI789RST", "JKL012MNO", "PQR345ABC"]
        response = mfa_schema.MFABackupCodesResponse(codes=codes, created_at=now)

        assert response.codes == codes
        assert response.created_at == now
        assert len(response.codes) == 5

    def test_backup_codes_response_with_10_codes(self):
        """Test backup codes response with 10 codes (typical use case)."""
        now = datetime.now(timezone.utc)
        codes = [f"CODE{i:05d}ABC" for i in range(10)]
        response = mfa_schema.MFABackupCodesResponse(codes=codes, created_at=now)

        assert len(response.codes) == 10
        assert response.codes[0] == "CODE00000ABC"
        assert response.codes[9] == "CODE00009ABC"

    def test_backup_codes_response_empty_list(self):
        """Test backup codes response with empty list."""
        now = datetime.now(timezone.utc)
        response = mfa_schema.MFABackupCodesResponse(codes=[], created_at=now)

        assert response.codes == []
        assert len(response.codes) == 0


class TestMFABackupCodeStatus:
    """Tests for MFABackupCodeStatus Pydantic model."""

    def test_valid_backup_code_status_with_codes(self):
        """Test valid backup code status with codes."""
        now = datetime.now(timezone.utc)
        status = mfa_schema.MFABackupCodeStatus(
            has_codes=True, total=10, unused=7, used=3, created_at=now
        )

        assert status.has_codes is True
        assert status.total == 10
        assert status.unused == 7
        assert status.used == 3
        assert status.created_at == now

    def test_backup_code_status_without_codes(self):
        """Test backup code status when user has no codes."""
        status = mfa_schema.MFABackupCodeStatus(
            has_codes=False, total=0, unused=0, used=0, created_at=None
        )

        assert status.has_codes is False
        assert status.total == 0
        assert status.unused == 0
        assert status.used == 0
        assert status.created_at is None

    def test_backup_code_status_all_used(self):
        """Test backup code status when all codes are used."""
        now = datetime.now(timezone.utc)
        status = mfa_schema.MFABackupCodeStatus(
            has_codes=True, total=10, unused=0, used=10, created_at=now
        )

        assert status.has_codes is True
        assert status.total == 10
        assert status.unused == 0
        assert status.used == 10

    def test_backup_code_status_all_unused(self):
        """Test backup code status when all codes are unused."""
        now = datetime.now(timezone.utc)
        status = mfa_schema.MFABackupCodeStatus(
            has_codes=True, total=10, unused=10, used=0, created_at=now
        )

        assert status.has_codes is True
        assert status.unused == 10
        assert status.used == 0

    def test_backup_code_status_fields_required(self):
        """Test that required fields are enforced."""
        with pytest.raises(ValidationError) as exc_info:
            mfa_schema.MFABackupCodeStatus(has_codes=True, total=10)
        assert "unused" in str(exc_info.value) or "used" in str(exc_info.value)

    def test_backup_code_status_created_at_optional(self):
        """Test that created_at is optional and defaults to None."""
        status = mfa_schema.MFABackupCodeStatus(
            has_codes=False, total=0, unused=0, used=0
        )

        assert status.created_at is None
