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

    @pytest.mark.parametrize("code", ["12345\u00b2", "\u0661\u0662\u0663\u0664\u0665\u0666"])
    def test_rejects_non_ascii_digits(self, code):
        with pytest.raises(ValidationError, match="MFA code must be"):
            mfa_schema.MFARequest(mfa_code=code)

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


class TestMFASetupRequest:
    """Test suite for MFASetupRequest schema."""

    def test_valid_with_code_and_empty_step_up(self):
        data = mfa_schema.MFASetupRequest(mfa_code="123456", step_up={})
        assert data.mfa_code == "123456"
        assert data.step_up.current_password is None

    def test_valid_with_code_and_password(self):
        data = mfa_schema.MFASetupRequest(mfa_code="654321", step_up={"current_password": "mypassword"})
        assert data.step_up.current_password == "mypassword"

    def test_step_up_is_required(self):
        with pytest.raises(ValidationError):
            mfa_schema.MFASetupRequest(mfa_code="123456")

    def test_flat_current_password_rejected(self):
        with pytest.raises(ValidationError):
            mfa_schema.MFASetupRequest(mfa_code="123456", step_up={}, current_password="mypassword")

    def test_rejects_non_digit_code(self):
        with pytest.raises(ValidationError):
            mfa_schema.MFASetupRequest(mfa_code="ABCDEF", step_up={})

    def test_rejects_non_ascii_digits(self):
        with pytest.raises(ValidationError):
            mfa_schema.MFASetupRequest(mfa_code="\u0661\u0662\u0663\u0664\u0665\u0666")

    def test_rejects_code_shorter_than_6(self):
        with pytest.raises(ValidationError):
            mfa_schema.MFASetupRequest(mfa_code="12345", step_up={})

    def test_rejects_code_longer_than_6(self):
        with pytest.raises(ValidationError):
            mfa_schema.MFASetupRequest(mfa_code="1234567", step_up={})

    def test_code_field_has_min_length_6(self):
        json_schema = mfa_schema.MFASetupRequest.model_json_schema()
        assert json_schema["properties"]["mfa_code"]["minLength"] == 6

    def test_code_field_has_max_length_6(self):
        json_schema = mfa_schema.MFASetupRequest.model_json_schema()
        assert json_schema["properties"]["mfa_code"]["maxLength"] == 6

    def test_code_field_has_pattern_digits(self):
        json_schema = mfa_schema.MFASetupRequest.model_json_schema()
        assert json_schema["properties"]["mfa_code"]["pattern"] == "^[0-9]{6}$"

    def test_empty_password_rejected(self):
        with pytest.raises(ValidationError):
            mfa_schema.MFASetupRequest(mfa_code="123456", step_up={"current_password": ""})

    def test_has_extra_forbid_config(self):
        assert mfa_schema.MFASetupRequest.model_config.get("extra") == "forbid"

    def test_has_validate_assignment_config(self):
        assert mfa_schema.MFASetupRequest.model_config.get("validate_assignment") is True


_BODIES = [
    (mfa_schema.MFASetupRequest, {"mfa_code": "123456", "step_up": {}}),
    (mfa_schema.MFADisableRequest, {"step_up": {}}),
    (mfa_schema.MFABackupCodesRequest, {"step_up": {}}),
]


class TestRevokeOtherSessionsOnMfaChanges:
    """The three second-factor changes end the caller's other sessions unless the client opts out."""

    @pytest.mark.parametrize(("schema", "body"), _BODIES, ids=[case[0].__name__ for case in _BODIES])
    def test_defaults_to_true_and_accepts_false(self, schema, body):
        assert schema(**body).revoke_other_sessions is True
        assert schema(**body, revoke_other_sessions=False).revoke_other_sessions is False

    @pytest.mark.parametrize(("schema", "body"), _BODIES, ids=[case[0].__name__ for case in _BODIES])
    def test_flag_is_strict_boolean(self, schema, body):
        with pytest.raises(ValidationError):
            schema(**body, revoke_other_sessions="yes")

    @pytest.mark.parametrize(("schema", "body"), _BODIES, ids=[case[0].__name__ for case in _BODIES])
    def test_forbids_extra_keys(self, schema, body):
        with pytest.raises(ValidationError) as exc:
            schema(**body, unexpected="value")
        assert exc.value.errors()[0]["type"] == "extra_forbidden"

    @pytest.mark.parametrize("schema", [mfa_schema.MFADisableRequest, mfa_schema.MFABackupCodesRequest])
    def test_step_up_is_required(self, schema):
        with pytest.raises(ValidationError) as exc:
            schema()
        assert exc.value.errors()[0]["type"] == "missing"


class TestMFASetupResponse:
    """Test suite for MFASetupRead schema."""

    def test_valid_response(self):
        data = mfa_schema.MFASetupRead(
            secret="JBSWY3DPEHPK3PXP",
            qr_code="data:image/png;base64,iVBORw0KGgo=",
        )
        assert data.secret == "JBSWY3DPEHPK3PXP"
        assert data.qr_code == "data:image/png;base64,iVBORw0KGgo="
        assert data.app_name == "Endurain"

    def test_custom_app_name(self):
        data = mfa_schema.MFASetupRead(
            secret="JBSWY3DPEHPK3PXP",
            qr_code="data:image/png;base64,test",
            app_name="CustomApp",
        )
        assert data.app_name == "CustomApp"

    def test_rejects_missing_secret(self):
        with pytest.raises(ValidationError):
            mfa_schema.MFASetupRead(qr_code="data:image/png;base64,test")

    def test_rejects_missing_qr_code(self):
        with pytest.raises(ValidationError):
            mfa_schema.MFASetupRead(secret="JBSWY3DPEHPK3PXP")

    def test_has_extra_forbid_config(self):
        assert mfa_schema.MFASetupRead.model_config.get("extra") == "forbid"


class TestMFAStatusResponse:
    """Test suite for MFAStatusRead schema."""

    def test_mfa_enabled_true(self):
        data = mfa_schema.MFAStatusRead(mfa_enabled=True)
        assert data.mfa_enabled is True

    def test_mfa_enabled_false(self):
        data = mfa_schema.MFAStatusRead(mfa_enabled=False)
        assert data.mfa_enabled is False

    def test_rejects_non_boolean(self):
        with pytest.raises(ValidationError):
            mfa_schema.MFAStatusRead(mfa_enabled="yes")

    def test_has_extra_forbid_config(self):
        assert mfa_schema.MFAStatusRead.model_config.get("extra") == "forbid"
