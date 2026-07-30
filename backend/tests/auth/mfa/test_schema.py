"""Tests for profile Pydantic schemas."""

import pytest
from pydantic import ValidationError

import modules.auth.mfa.schema as mfa_schema


class TestMFARequest:
    """Test suite for MFARequest schema."""

    def test_valid_6_digit_code(self):
        data = mfa_schema.MFARequest(mfa_code="123456")
        assert data.mfa_code == "123456"

    def test_valid_9_char_backup_code(self):
        data = mfa_schema.MFARequest(mfa_code="ABCD-EFGH")
        assert data.mfa_code == "ABCD-EFGH"

    def test_normalizes_lowercase_to_uppercase(self):
        data = mfa_schema.MFARequest(mfa_code="abcd-efgh")
        assert data.mfa_code == "ABCD-EFGH"

    def test_strips_whitespace(self):
        data = mfa_schema.MFARequest(mfa_code="123456  ")
        assert data.mfa_code == "123456"

    def test_rejects_5_digit_code(self):
        with pytest.raises(ValidationError):
            mfa_schema.MFARequest(mfa_code="12345")

    def test_rejects_10_char_code(self):
        with pytest.raises(ValidationError):
            mfa_schema.MFARequest(mfa_code="ABCD-EFGHI")

    def test_rejects_code_without_dash_at_position_4(self):
        with pytest.raises(ValidationError, match="MFA code must be"):
            mfa_schema.MFARequest(mfa_code="ABCDEFGHI")

    def test_rejects_empty_string(self):
        with pytest.raises(ValidationError):
            mfa_schema.MFARequest(mfa_code="")

    def test_rejects_extra_fields(self):
        with pytest.raises(ValidationError):
            mfa_schema.MFARequest(mfa_code="123456", extra_field="test")

    def test_has_extra_forbid_config(self):
        assert mfa_schema.MFARequest.model_config.get("extra") == "forbid"

    def test_has_validate_assignment_config(self):
        assert mfa_schema.MFARequest.model_config.get("validate_assignment") is True


class TestMFADisableRequest:
    """Test suite for MFADisableRequest schema."""

    def test_valid_with_code_only(self):
        data = mfa_schema.MFADisableRequest(mfa_code="123456")
        assert data.mfa_code == "123456"
        assert data.current_password is None

    def test_valid_with_code_and_password(self):
        data = mfa_schema.MFADisableRequest(mfa_code="123456", current_password="mypassword")
        assert data.current_password == "mypassword"

    def test_inherits_mfa_code_validation(self):
        with pytest.raises(ValidationError):
            mfa_schema.MFADisableRequest(mfa_code="123")

    def test_empty_password_rejected(self):
        with pytest.raises(ValidationError):
            mfa_schema.MFADisableRequest(mfa_code="123456", current_password="")

    def test_has_extra_forbid_config(self):
        assert mfa_schema.MFADisableRequest.model_config.get("extra") == "forbid"

    def test_has_validate_assignment_config(self):
        assert mfa_schema.MFADisableRequest.model_config.get("validate_assignment") is True


class TestMFASetupRequest:
    """Test suite for MFASetupRequest schema."""

    def test_valid_with_code_only(self):
        data = mfa_schema.MFASetupRequest(mfa_code="123456")
        assert data.mfa_code == "123456"
        assert data.current_password is None

    def test_valid_with_code_and_password(self):
        data = mfa_schema.MFASetupRequest(mfa_code="654321", current_password="mypassword")
        assert data.current_password == "mypassword"

    def test_rejects_non_digit_code(self):
        with pytest.raises(ValidationError):
            mfa_schema.MFASetupRequest(mfa_code="ABCDEF")

    def test_rejects_code_shorter_than_6(self):
        with pytest.raises(ValidationError):
            mfa_schema.MFASetupRequest(mfa_code="12345")

    def test_rejects_code_longer_than_6(self):
        with pytest.raises(ValidationError):
            mfa_schema.MFASetupRequest(mfa_code="1234567")

    def test_code_field_has_min_length_6(self):
        json_schema = mfa_schema.MFASetupRequest.model_json_schema()
        assert json_schema["properties"]["mfa_code"]["minLength"] == 6

    def test_code_field_has_max_length_6(self):
        json_schema = mfa_schema.MFASetupRequest.model_json_schema()
        assert json_schema["properties"]["mfa_code"]["maxLength"] == 6

    def test_code_field_has_pattern_digits(self):
        json_schema = mfa_schema.MFASetupRequest.model_json_schema()
        assert json_schema["properties"]["mfa_code"]["pattern"] == "^\\d{6}$"

    def test_empty_password_rejected(self):
        with pytest.raises(ValidationError):
            mfa_schema.MFASetupRequest(mfa_code="123456", current_password="")

    def test_has_extra_forbid_config(self):
        assert mfa_schema.MFASetupRequest.model_config.get("extra") == "forbid"

    def test_has_validate_assignment_config(self):
        assert mfa_schema.MFASetupRequest.model_config.get("validate_assignment") is True


class TestMFASetupResponse:
    """Test suite for MFASetupResponse schema."""

    def test_valid_response(self):
        data = mfa_schema.MFASetupResponse(
            secret="JBSWY3DPEHPK3PXP",
            qr_code="data:image/png;base64,iVBORw0KGgo=",
        )
        assert data.secret == "JBSWY3DPEHPK3PXP"
        assert data.qr_code == "data:image/png;base64,iVBORw0KGgo="
        assert data.app_name == "Endurain"

    def test_custom_app_name(self):
        data = mfa_schema.MFASetupResponse(
            secret="JBSWY3DPEHPK3PXP",
            qr_code="data:image/png;base64,test",
            app_name="CustomApp",
        )
        assert data.app_name == "CustomApp"

    def test_rejects_missing_secret(self):
        with pytest.raises(ValidationError):
            mfa_schema.MFASetupResponse(qr_code="data:image/png;base64,test")

    def test_rejects_missing_qr_code(self):
        with pytest.raises(ValidationError):
            mfa_schema.MFASetupResponse(secret="JBSWY3DPEHPK3PXP")

    def test_has_extra_forbid_config(self):
        assert mfa_schema.MFASetupResponse.model_config.get("extra") == "forbid"


class TestMFAStatusResponse:
    """Test suite for MFAStatusResponse schema."""

    def test_mfa_enabled_true(self):
        data = mfa_schema.MFAStatusResponse(mfa_enabled=True)
        assert data.mfa_enabled is True

    def test_mfa_enabled_false(self):
        data = mfa_schema.MFAStatusResponse(mfa_enabled=False)
        assert data.mfa_enabled is False

    def test_rejects_non_boolean(self):
        with pytest.raises(ValidationError):
            mfa_schema.MFAStatusResponse(mfa_enabled="yes")

    def test_has_extra_forbid_config(self):
        assert mfa_schema.MFAStatusResponse.model_config.get("extra") == "forbid"
