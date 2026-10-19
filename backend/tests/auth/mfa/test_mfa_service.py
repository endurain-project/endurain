"""Tests for auth.mfa.service (moved from profile.utils)."""

from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException, status

import modules.auth.mfa.service as mfa_service


class TestGenerateTOTPSecret:
    """Test suite for generate_totp_secret function."""

    @patch("modules.auth.mfa.service.pyotp.random_base32")
    def test_returns_base32_secret(self, mock_random_base32):
        mock_random_base32.return_value = "JBSWY3DPEHPK3PXP"

        result = mfa_service.generate_totp_secret()

        assert result == "JBSWY3DPEHPK3PXP"
        mock_random_base32.assert_called_once()


class TestVerifyTOTP:
    """Test suite for verify_totp function."""

    @patch("modules.auth.mfa.service.pyotp.TOTP")
    def test_verify_valid_token(self, mock_totp_class):
        mock_totp = MagicMock()
        mock_totp.verify.return_value = True
        mock_totp_class.return_value = mock_totp

        result = mfa_service.verify_totp("secret", "123456")
        assert result is True
        mock_totp.verify.assert_called_once_with("123456", valid_window=1)

    @patch("modules.auth.mfa.service.pyotp.TOTP")
    def test_verify_invalid_token(self, mock_totp_class):
        mock_totp = MagicMock()
        mock_totp.verify.return_value = False
        mock_totp_class.return_value = mock_totp

        result = mfa_service.verify_totp("secret", "000000")
        assert result is False


class TestGenerateQRCode:
    """Test suite for generate_qr_code function."""

    @patch("modules.auth.mfa.service.qrcode.QRCode")
    @patch("modules.auth.mfa.service.pyotp.TOTP")
    def test_generates_qr_code(self, mock_totp_class, mock_qr_class):
        mock_totp = MagicMock()
        mock_totp.provisioning_uri.return_value = "otpauth://totp/Endurain:testuser?secret=SECRET"
        mock_totp_class.return_value = mock_totp

        mock_qr = MagicMock()
        mock_qr_class.return_value = mock_qr

        mock_img = MagicMock()
        mock_qr.make_image.return_value = mock_img

        mock_img.save = MagicMock()

        with patch("modules.auth.mfa.service.BytesIO") as mock_bytesio:
            mock_buffer = MagicMock()
            mock_bytesio.return_value = mock_buffer
            mock_buffer.getvalue.return_value = b"png_data"

            with patch("modules.auth.mfa.service.base64.b64encode") as mock_b64:
                mock_b64.return_value = b"cG5nX2RhdGE="
                result = mfa_service.generate_qr_code("SECRET", "testuser")

        assert result == "data:image/png;base64,cG5nX2RhdGE="
        mock_totp.provisioning_uri.assert_called_once_with(name="testuser", issuer_name="Endurain")
        mock_qr.add_data.assert_called_once_with("otpauth://totp/Endurain:testuser?secret=SECRET")
        mock_qr.make.assert_called_once_with(fit=True)

    @patch("modules.auth.mfa.service.pyotp.TOTP")
    def test_generates_qr_code_with_custom_app_name(self, mock_totp_class):
        mock_totp = MagicMock()
        mock_totp.provisioning_uri.return_value = "otpauth://totp/CustomApp:testuser?secret=SECRET"
        mock_totp_class.return_value = mock_totp

        with patch("modules.auth.mfa.service.qrcode.QRCode") as mock_qr_class:
            mock_qr = MagicMock()
            mock_qr_class.return_value = mock_qr
            mock_img = MagicMock()
            mock_qr.make_image.return_value = mock_img

            with patch("modules.auth.mfa.service.BytesIO") as mock_bytesio:
                mock_buffer = MagicMock()
                mock_bytesio.return_value = mock_buffer
                mock_buffer.getvalue.return_value = b"png_data"

                with patch("modules.auth.mfa.service.base64.b64encode") as mock_b64:
                    mock_b64.return_value = b"cG5nX2RhdGE="
                    result = mfa_service.generate_qr_code("SECRET", "testuser", "CustomApp")

        mock_totp.provisioning_uri.assert_called_once_with(name="testuser", issuer_name="CustomApp")
        assert "data:image/png;base64" in result


class TestSetupUserMFA:
    """Test suite for setup_user_mfa function."""

    @patch("modules.auth.mfa.service.generate_qr_code")
    @patch("modules.auth.mfa.service.generate_totp_secret")
    @patch("modules.auth.mfa.service.users_utils.get_user_by_id_or_404")
    def test_successful_setup(self, mock_get_user, mock_gen_secret, mock_gen_qr):
        mock_user = MagicMock()
        mock_user.username = "testuser"
        mock_user.mfa_enabled = False
        mock_get_user.return_value = mock_user
        mock_gen_secret.return_value = "NEWSECRET"
        mock_gen_qr.return_value = "data:image/png;base64,QRCODE"

        with patch("modules.auth.mfa.service.is_mfa_enabled_for_user", return_value=False):
            result = mfa_service.setup_user_mfa(1, MagicMock())

        assert result.secret == "NEWSECRET"
        assert result.qr_code == "data:image/png;base64,QRCODE"
        assert result.app_name == "Endurain"
        mock_gen_qr.assert_called_once_with("NEWSECRET", "testuser")

    @patch("modules.auth.mfa.service.users_utils.get_user_by_id_or_404")
    def test_user_not_found(self, mock_get_user):
        mock_get_user.side_effect = HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )

        with pytest.raises(Exception) as exc_info:
            mfa_service.setup_user_mfa(1, MagicMock())

        assert exc_info.typename == "HTTPException"
        assert exc_info.value.status_code == 404

    @patch("modules.auth.mfa.service.users_utils.get_user_by_id_or_404")
    def test_mfa_already_enabled(self, mock_get_user):
        mock_user = MagicMock()
        mock_user.mfa_enabled = True
        mock_get_user.return_value = mock_user

        with pytest.raises(Exception) as exc_info:
            mfa_service.setup_user_mfa(1, MagicMock())

        assert exc_info.typename == "HTTPException"
        assert exc_info.value.status_code == 400


class TestEnableUserMFA:
    """Test suite for enable_user_mfa function."""

    @patch("modules.auth.mfa.service.mfa_backup_codes_crud.create_backup_codes")
    @patch("modules.auth.mfa.service.verify_totp")
    @patch("modules.auth.mfa.service.core_cryptography.encrypt_token_fernet")
    @patch("modules.auth.mfa.service.auth_mfa_crud.update_user_mfa")
    @patch("modules.auth.mfa.service.users_utils.get_user_by_id_or_404")
    def test_successful_enable(self, mock_get_user, mock_update_mfa, mock_encrypt, mock_verify, mock_create_backup):
        mock_user = MagicMock()
        mock_user.mfa_enabled = False
        mock_get_user.return_value = mock_user
        mock_encrypt.return_value = "encrypted_secret"
        mock_verify.return_value = True
        mock_create_backup.return_value = ["CODE1", "CODE2"]

        mock_identity_service = MagicMock()

        with patch("modules.auth.mfa.service.is_mfa_enabled_for_user", return_value=False):
            result = mfa_service.enable_user_mfa(1, "secret", "123456", mock_identity_service, MagicMock())

        assert result == ["CODE1", "CODE2"]
        mock_update_mfa.assert_called_once()
        mock_create_backup.assert_called_once_with(1, mock_identity_service, mock_create_backup.call_args[0][2])

    @patch("modules.auth.mfa.service.users_utils.get_user_by_id_or_404")
    def test_user_not_found(self, mock_get_user):
        mock_get_user.side_effect = HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )

        with pytest.raises(Exception) as exc_info:
            mfa_service.enable_user_mfa(1, "secret", "123456", MagicMock(), MagicMock())

        assert exc_info.typename == "HTTPException"
        assert exc_info.value.status_code == 404

    @patch("modules.auth.mfa.service.users_utils.get_user_by_id_or_404")
    def test_mfa_already_enabled(self, mock_get_user):
        mock_user = MagicMock()
        mock_user.mfa_enabled = True
        mock_get_user.return_value = mock_user

        with pytest.raises(Exception) as exc_info:
            mfa_service.enable_user_mfa(1, "secret", "123456", MagicMock(), MagicMock())

        assert exc_info.typename == "HTTPException"
        assert exc_info.value.status_code == 400

    @patch("modules.auth.mfa.service.verify_totp")
    @patch("modules.auth.mfa.service.users_utils.get_user_by_id_or_404")
    def test_invalid_mfa_code(self, mock_get_user, mock_verify):
        mock_user = MagicMock()
        mock_user.mfa_enabled = False
        mock_get_user.return_value = mock_user
        mock_verify.return_value = False

        with (
            patch("modules.auth.mfa.service.is_mfa_enabled_for_user", return_value=False),
            pytest.raises(Exception) as exc_info,
        ):
            mfa_service.enable_user_mfa(1, "secret", "000000", MagicMock(), MagicMock())

        assert exc_info.typename == "HTTPException"
        assert exc_info.value.status_code == 400

    @patch("modules.auth.mfa.service.verify_totp")
    @patch("modules.auth.mfa.service.core_cryptography.encrypt_token_fernet")
    @patch("modules.auth.mfa.service.users_utils.get_user_by_id_or_404")
    def test_encryption_failure(self, mock_get_user, mock_encrypt, mock_verify):
        mock_user = MagicMock()
        mock_user.mfa_enabled = False
        mock_get_user.return_value = mock_user
        mock_encrypt.return_value = None
        mock_verify.return_value = True

        with (
            patch("modules.auth.mfa.service.is_mfa_enabled_for_user", return_value=False),
            pytest.raises(Exception) as exc_info,
        ):
            mfa_service.enable_user_mfa(1, "secret", "123456", MagicMock(), MagicMock())

        assert exc_info.typename == "HTTPException"
        assert exc_info.value.status_code == 500


class TestDisableUserMFA:
    """Test suite for disable_user_mfa function."""

    @patch("modules.auth.mfa.service.mfa_backup_codes_crud.delete_user_backup_codes")
    @patch("modules.auth.mfa.service.auth_mfa_crud.update_user_mfa")
    @patch("modules.auth.mfa.service.users_utils.get_user_by_id_or_404")
    def test_successful_disable(self, mock_get_user, mock_update_mfa, mock_delete_codes):
        mock_user = MagicMock()
        mock_user.mfa_enabled = True
        mock_get_user.return_value = mock_user

        mfa_service.disable_user_mfa(1, MagicMock())

        mock_update_mfa.assert_called_once()
        mock_delete_codes.assert_called_once()

    @patch("modules.auth.mfa.service.users_utils.get_user_by_id_or_404")
    def test_user_not_found(self, mock_get_user):
        mock_get_user.side_effect = HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )

        with pytest.raises(Exception) as exc_info:
            mfa_service.disable_user_mfa(1, MagicMock())

        assert exc_info.typename == "HTTPException"
        assert exc_info.value.status_code == 404

    @patch("modules.auth.mfa.service.users_utils.get_user_by_id_or_404")
    def test_mfa_not_enabled(self, mock_get_user):
        mock_user = MagicMock()
        mock_user.mfa_enabled = False
        mock_get_user.return_value = mock_user

        with (
            patch("modules.auth.mfa.service.is_mfa_enabled_for_user", return_value=False),
            pytest.raises(Exception) as exc_info,
        ):
            mfa_service.disable_user_mfa(1, MagicMock())

        assert exc_info.typename == "HTTPException"
        assert exc_info.value.status_code == 400


class TestVerifyUserMFA:
    """Test suite for verify_user_mfa function."""

    @pytest.fixture(autouse=True)
    def _wire_mfa_row(self):
        """Mirror auth_mfa_crud.get_user_mfa_row to the mocked user's auth_mfa.

        Production reads the ``users_mfa`` row via
        ``auth_mfa_crud.get_user_mfa_row`` rather than a
        ``UsersRead.auth_mfa`` relationship (which the API schema does not
        expose), so resolve the row from the patched user mock.
        """

        def _row(_user_id, _db):
            user = mfa_service.users_utils.get_user_by_id_or_404.return_value
            return getattr(user, "auth_mfa", None)

        with patch("modules.auth.mfa.service.auth_mfa_crud.get_user_mfa_row", side_effect=_row):
            yield

    @patch("modules.auth.mfa.service.verify_totp")
    @patch("modules.auth.mfa.service.core_cryptography.decrypt_token_fernet")
    @patch("modules.auth.mfa.service.users_utils.get_user_by_id_or_404")
    def test_totp_verification_success(self, mock_get_user, mock_decrypt, mock_verify):
        mock_user = MagicMock()
        mock_user.auth_mfa.mfa_enabled = True
        mock_user.auth_mfa.mfa_secret = "encrypted_secret"
        mock_get_user.return_value = mock_user
        mock_decrypt.return_value = "decrypted_secret"
        mock_verify.return_value = True

        result = mfa_service.verify_user_mfa(1, "123456", MagicMock(), MagicMock())
        assert result is True
        mock_decrypt.assert_called_once_with("encrypted_secret")
        mock_verify.assert_called_once_with("decrypted_secret", "123456")

    @patch("modules.auth.mfa.service.verify_totp")
    @patch("modules.auth.mfa.service.core_cryptography.decrypt_token_fernet")
    @patch("modules.auth.mfa.service.users_utils.get_user_by_id_or_404")
    def test_totp_verify_value_error_returns_false(self, mock_get_user, mock_decrypt, mock_verify):
        mock_user = MagicMock()
        mock_user.auth_mfa.mfa_enabled = True
        mock_user.auth_mfa.mfa_secret = "encrypted_secret"
        mock_get_user.return_value = mock_user
        mock_decrypt.return_value = "decrypted_secret"
        mock_verify.side_effect = ValueError("invalid token")

        result = mfa_service.verify_user_mfa(1, "123456", MagicMock(), MagicMock())
        assert result is False

    @patch("modules.auth.mfa.service.verify_totp")
    @patch("modules.auth.mfa.service.core_cryptography.decrypt_token_fernet")
    @patch("modules.auth.mfa.service.users_utils.get_user_by_id_or_404")
    def test_totp_verify_unexpected_exception_propagates(self, mock_get_user, mock_decrypt, mock_verify):
        """Unexpected non-OTP errors bubble up instead of being swallowed as False."""
        mock_user = MagicMock()
        mock_user.auth_mfa.mfa_enabled = True
        mock_user.auth_mfa.mfa_secret = "encrypted_secret"
        mock_get_user.return_value = mock_user
        mock_decrypt.return_value = "decrypted_secret"
        mock_verify.side_effect = RuntimeError("unexpected infrastructure error")

        with pytest.raises(RuntimeError, match="unexpected infrastructure error"):
            mfa_service.verify_user_mfa(1, "123456", MagicMock(), MagicMock())

    @patch("modules.auth.mfa.service.users_utils.get_user_by_id_or_404")
    def test_user_not_found(self, mock_get_user):
        mock_get_user.side_effect = HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )

        with pytest.raises(Exception) as exc_info:
            mfa_service.verify_user_mfa(1, "123456", MagicMock(), MagicMock())

        assert exc_info.typename == "HTTPException"
        assert exc_info.value.status_code == 404

    @patch("modules.auth.mfa.service.users_utils.get_user_by_id_or_404")
    def test_mfa_not_enabled_returns_false(self, mock_get_user):
        mock_user = MagicMock()
        mock_user.auth_mfa = None
        mock_get_user.return_value = mock_user

        result = mfa_service.verify_user_mfa(1, "123456", MagicMock(), MagicMock())
        assert result is False

    @patch("modules.auth.mfa.service.users_utils.get_user_by_id_or_404")
    def test_mfa_disabled_returns_false(self, mock_get_user):
        mock_user = MagicMock()
        mock_user.auth_mfa.mfa_enabled = False
        mock_get_user.return_value = mock_user

        result = mfa_service.verify_user_mfa(1, "123456", MagicMock(), MagicMock())
        assert result is False

    @patch("modules.auth.mfa.service.users_utils.get_user_by_id_or_404")
    def test_mfa_no_secret_returns_false(self, mock_get_user):
        mock_user = MagicMock()
        mock_user.auth_mfa.mfa_enabled = True
        mock_user.auth_mfa.mfa_secret = None
        mock_get_user.return_value = mock_user

        result = mfa_service.verify_user_mfa(1, "123456", MagicMock(), MagicMock())
        assert result is False

    @patch("modules.auth.mfa.service.core_cryptography.decrypt_token_fernet")
    @patch("modules.auth.mfa.service.users_utils.get_user_by_id_or_404")
    def test_totp_decrypt_failure_returns_false(self, mock_get_user, mock_decrypt):
        mock_user = MagicMock()
        mock_user.auth_mfa.mfa_enabled = True
        mock_user.auth_mfa.mfa_secret = "encrypted_secret"
        mock_get_user.return_value = mock_user
        mock_decrypt.return_value = None

        result = mfa_service.verify_user_mfa(1, "123456", MagicMock(), MagicMock())
        assert result is False

    @patch("modules.auth.mfa.service.verify_totp")
    @patch("modules.auth.mfa.service.core_cryptography.decrypt_token_fernet")
    @patch("modules.auth.mfa.service.users_utils.get_user_by_id_or_404")
    def test_backup_code_verification_success(self, mock_get_user, mock_decrypt, mock_verify):
        mock_user = MagicMock()
        mock_user.auth_mfa.mfa_enabled = True
        mock_user.auth_mfa.mfa_secret = "encrypted_secret"
        mock_get_user.return_value = mock_user
        mock_verify.return_value = False

        mock_identity_service = MagicMock()

        with patch(
            "modules.auth.mfa.service.mfa_backup_codes_utils.verify_and_consume_backup_code", return_value=True
        ) as mock_backup:
            result = mfa_service.verify_user_mfa(1, "ABCD-EFGH", mock_identity_service, MagicMock())
            assert result is True
            mock_backup.assert_called_once_with(1, "ABCD-EFGH", mock_identity_service, mock_backup.call_args[0][3])

    @patch("modules.auth.mfa.service.verify_totp")
    @patch("modules.auth.mfa.service.core_cryptography.decrypt_token_fernet")
    @patch("modules.auth.mfa.service.users_utils.get_user_by_id_or_404")
    def test_backup_code_verification_failure_returns_false(self, mock_get_user, mock_decrypt, mock_verify):
        mock_user = MagicMock()
        mock_user.auth_mfa.mfa_enabled = True
        mock_user.auth_mfa.mfa_secret = "encrypted_secret"
        mock_get_user.return_value = mock_user
        mock_verify.return_value = False

        mock_identity_service = MagicMock()

        with patch(
            "modules.auth.mfa.service.mfa_backup_codes_utils.verify_and_consume_backup_code", return_value=False
        ):
            result = mfa_service.verify_user_mfa(1, "ABCD-EFGH", mock_identity_service, MagicMock())
            assert result is False

    @patch("modules.auth.mfa.service.users_utils.get_user_by_id_or_404")
    def test_invalid_code_format_returns_false(self, mock_get_user):
        mock_user = MagicMock()
        mock_user.auth_mfa.mfa_enabled = True
        mock_user.auth_mfa.mfa_secret = "encrypted_secret"
        mock_get_user.return_value = mock_user

        result = mfa_service.verify_user_mfa(1, "invalid", MagicMock(), MagicMock())
        assert result is False

    @patch("modules.auth.mfa.service.verify_totp")
    @patch("modules.auth.mfa.service.core_cryptography.decrypt_token_fernet")
    @patch("modules.auth.mfa.service.users_utils.get_user_by_id_or_404")
    def test_backup_code_unexpected_exception_propagates(self, mock_get_user, mock_decrypt, mock_verify):
        """Unexpected errors from backup-code verification propagate to the global handler.

        Backup-code verification does not swallow unexpected exceptions; only
        legitimate False returns map to a failed check.
        """
        mock_user = MagicMock()
        mock_user.auth_mfa.mfa_enabled = True
        mock_user.auth_mfa.mfa_secret = "encrypted_secret"
        mock_get_user.return_value = mock_user
        mock_verify.return_value = False

        mock_identity_service = MagicMock()

        with (
            patch(
                "modules.auth.mfa.service.mfa_backup_codes_utils.verify_and_consume_backup_code",
                side_effect=RuntimeError("storage failure"),
            ),
            pytest.raises(RuntimeError, match="storage failure"),
        ):
            mfa_service.verify_user_mfa(1, "ABCD-EFGH", mock_identity_service, MagicMock())


class TestIsMFAEnabledForUser:
    """Test suite for is_mfa_enabled_for_user function."""

    @pytest.fixture(autouse=True)
    def _wire_mfa_row(self):
        """Mirror auth_mfa_crud.get_user_mfa_row to the mocked user's auth_mfa.

        Production reads the ``users_mfa`` row via
        ``auth_mfa_crud.get_user_mfa_row`` rather than a
        ``UsersRead.auth_mfa`` relationship (which the API schema does not
        expose), so resolve the row from the patched user mock.
        """

        def _row(_user_id, _db):
            user = mfa_service.users_utils.get_user_by_id_or_404.return_value
            return getattr(user, "auth_mfa", None)

        with patch("modules.auth.mfa.service.auth_mfa_crud.get_user_mfa_row", side_effect=_row):
            yield

    @patch("modules.auth.mfa.service.users_utils.get_user_by_id_or_404")
    def test_mfa_enabled(self, mock_get_user):
        mock_user = MagicMock()
        mock_user.auth_mfa.mfa_enabled = True
        mock_user.auth_mfa.mfa_secret = "secret"
        mock_get_user.return_value = mock_user

        result = mfa_service.is_mfa_enabled_for_user(1, MagicMock())
        assert result is True

    @patch("modules.auth.mfa.service.users_utils.get_user_by_id_or_404")
    def test_user_not_found_returns_false(self, mock_get_user):
        mock_get_user.side_effect = HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )

        result = mfa_service.is_mfa_enabled_for_user(1, MagicMock())
        assert result is False

    @patch("modules.auth.mfa.service.users_utils.get_user_by_id_or_404")
    def test_mfa_not_enabled_returns_false(self, mock_get_user):
        mock_user = MagicMock()
        mock_user.auth_mfa = None
        mock_get_user.return_value = mock_user

        result = mfa_service.is_mfa_enabled_for_user(1, MagicMock())
        assert result is False

    @patch("modules.auth.mfa.service.users_utils.get_user_by_id_or_404")
    def test_mfa_disabled_returns_false(self, mock_get_user):
        mock_user = MagicMock()
        mock_user.auth_mfa.mfa_enabled = False
        mock_get_user.return_value = mock_user

        result = mfa_service.is_mfa_enabled_for_user(1, MagicMock())
        assert result is False

    @patch("modules.auth.mfa.service.users_utils.get_user_by_id_or_404")
    def test_mfa_no_secret_returns_false(self, mock_get_user):
        mock_user = MagicMock()
        mock_user.auth_mfa.mfa_enabled = True
        mock_user.auth_mfa.mfa_secret = None
        mock_get_user.return_value = mock_user

        result = mfa_service.is_mfa_enabled_for_user(1, MagicMock())
        assert result is False
