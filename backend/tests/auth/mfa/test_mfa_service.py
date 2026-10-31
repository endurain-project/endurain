"""Tests for auth.mfa.service (moved from profile.utils)."""

from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pyotp
import pytest

import core.exceptions as core_exceptions
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

    def test_verify_valid_token(self):
        secret = pyotp.random_base32()

        assert mfa_service.verify_totp(secret, pyotp.TOTP(secret).now()) is True

    def test_verify_invalid_token(self):
        secret = pyotp.random_base32()
        wrong = "000000" if pyotp.TOTP(secret).now() != "000000" else "111111"

        assert mfa_service.verify_totp(secret, wrong) is False


class TestVerifyUserMfaTotpReplay:
    """A TOTP step is accepted once per user, so an observed code cannot be replayed."""

    _SECRET = "JBSWY3DPEHPK3PXP"

    def _verify(self, code, guard):
        row = SimpleNamespace(mfa_enabled=True, mfa_secret="encrypted")
        with (
            patch("modules.auth.mfa.service.users_integration.require_user", return_value=SimpleNamespace(id=1)),
            patch("modules.auth.mfa.service.auth_mfa_crud.get_user_mfa_row", return_value=row),
            patch("modules.auth.mfa.service.core_cryptography.decrypt_token_fernet", return_value=self._SECRET),
        ):
            return mfa_service.verify_user_mfa(1, code, MagicMock(), MagicMock(), replay_guard=guard)

    def test_a_fresh_code_is_accepted_and_its_step_claimed(self):
        guard = MagicMock()
        guard.claim_totp_step.return_value = True
        totp = pyotp.TOTP(self._SECRET)

        assert self._verify(totp.now(), guard) is True

        user_id, step = guard.claim_totp_step.call_args.args
        assert user_id == 1
        assert abs(step - totp.timecode(datetime.now(UTC))) <= 1

    def test_a_code_whose_step_was_already_used_is_rejected(self):
        guard = MagicMock()
        guard.claim_totp_step.return_value = False

        assert self._verify(pyotp.TOTP(self._SECRET).now(), guard) is False

    def test_a_wrong_code_claims_nothing(self):
        guard = MagicMock()
        wrong = "000000" if pyotp.TOTP(self._SECRET).now() != "000000" else "111111"

        assert self._verify(wrong, guard) is False
        guard.claim_totp_step.assert_not_called()


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
    @patch("modules.auth.mfa.service.users_integration.require_user")
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

    @patch("modules.auth.mfa.service.users_integration.require_user")
    def test_user_not_found(self, mock_get_user):
        mock_get_user.side_effect = core_exceptions.NotFoundError("User not found")

        with pytest.raises(core_exceptions.NotFoundError):
            mfa_service.setup_user_mfa(1, MagicMock())

    @patch("modules.auth.mfa.service.users_integration.require_user")
    def test_mfa_already_enabled(self, mock_get_user):
        mock_user = MagicMock()
        mock_user.mfa_enabled = True
        mock_get_user.return_value = mock_user

        with (
            patch("modules.auth.mfa.service.is_mfa_enabled_for_user", return_value=True),
            pytest.raises(core_exceptions.InvalidInputError),
        ):
            mfa_service.setup_user_mfa(1, MagicMock())


class TestEnableUserMFA:
    """Test suite for enable_user_mfa function."""

    @patch("modules.auth.mfa.service.mfa_backup_codes_integration.create_backup_codes")
    @patch("modules.auth.mfa.service.mfa_totp_replay_store.matching_totp_step")
    @patch("modules.auth.mfa.service.core_cryptography.encrypt_token_fernet")
    @patch("modules.auth.mfa.service.auth_mfa_crud.update_user_mfa")
    @patch("modules.auth.mfa.service.users_integration.require_user")
    def test_successful_enable(self, mock_get_user, mock_update_mfa, mock_encrypt, mock_verify, mock_create_backup):
        mock_user = MagicMock()
        mock_user.mfa_enabled = False
        mock_get_user.return_value = mock_user
        mock_encrypt.return_value = "encrypted_secret"
        mock_verify.return_value = 7
        mock_create_backup.return_value = ["CODE1", "CODE2"]

        mock_password_verifier = MagicMock()

        mock_db = MagicMock()
        with patch("modules.auth.mfa.service.is_mfa_enabled_for_user", return_value=False):
            result = mfa_service.enable_user_mfa(1, "secret", "123456", mock_password_verifier, mock_db)

        assert result == ["CODE1", "CODE2"]
        mock_update_mfa.assert_called_once()
        mock_create_backup.assert_called_once_with(1, mock_password_verifier, mock_create_backup.call_args[0][2])
        mock_db.commit.assert_not_called()

    @patch("modules.auth.mfa.service.users_integration.require_user")
    def test_user_not_found(self, mock_get_user):
        mock_get_user.side_effect = core_exceptions.NotFoundError("User not found")

        with pytest.raises(core_exceptions.NotFoundError):
            mfa_service.enable_user_mfa(1, "secret", "123456", MagicMock(), MagicMock())

    @patch("modules.auth.mfa.service.users_integration.require_user")
    def test_mfa_already_enabled(self, mock_get_user):
        mock_user = MagicMock()
        mock_user.mfa_enabled = True
        mock_get_user.return_value = mock_user

        with (
            patch("modules.auth.mfa.service.is_mfa_enabled_for_user", return_value=True),
            pytest.raises(core_exceptions.InvalidInputError),
        ):
            mfa_service.enable_user_mfa(1, "secret", "123456", MagicMock(), MagicMock())

    @patch("modules.auth.mfa.service.mfa_totp_replay_store.matching_totp_step")
    @patch("modules.auth.mfa.service.users_integration.require_user")
    def test_invalid_mfa_code(self, mock_get_user, mock_verify):
        mock_user = MagicMock()
        mock_user.mfa_enabled = False
        mock_get_user.return_value = mock_user
        mock_verify.return_value = None

        with (
            patch("modules.auth.mfa.service.is_mfa_enabled_for_user", return_value=False),
            pytest.raises(core_exceptions.InvalidInputError),
        ):
            mfa_service.enable_user_mfa(1, "secret", "000000", MagicMock(), MagicMock())

    @patch("modules.auth.mfa.service.mfa_totp_replay_store.matching_totp_step")
    @patch("modules.auth.mfa.service.core_cryptography.encrypt_token_fernet")
    @patch("modules.auth.mfa.service.users_integration.require_user")
    def test_encryption_failure(self, mock_get_user, mock_encrypt, mock_verify):
        mock_user = MagicMock()
        mock_user.mfa_enabled = False
        mock_get_user.return_value = mock_user
        mock_encrypt.return_value = None
        mock_verify.return_value = 7

        with (
            patch("modules.auth.mfa.service.is_mfa_enabled_for_user", return_value=False),
            pytest.raises(core_exceptions.ProcessingError),
        ):
            mfa_service.enable_user_mfa(1, "secret", "123456", MagicMock(), MagicMock())


class TestDisableUserMFA:
    """Test suite for disable_user_mfa function."""

    @patch("modules.auth.mfa.service.mfa_backup_codes_integration.delete_user_backup_codes")
    @patch("modules.auth.mfa.service.auth_mfa_crud.update_user_mfa")
    @patch("modules.auth.mfa.service.users_integration.require_user")
    def test_successful_disable(self, mock_get_user, mock_update_mfa, mock_delete_codes):
        mock_user = MagicMock()
        mock_user.mfa_enabled = True
        mock_get_user.return_value = mock_user

        with patch("modules.auth.mfa.service.is_mfa_enabled_for_user", return_value=True):
            mfa_service.disable_user_mfa(1, MagicMock())

        mock_update_mfa.assert_called_once()
        mock_delete_codes.assert_called_once()

    @patch("modules.auth.mfa.service.users_integration.require_user")
    def test_user_not_found(self, mock_get_user):
        mock_get_user.side_effect = core_exceptions.NotFoundError("User not found")

        with pytest.raises(core_exceptions.NotFoundError):
            mfa_service.disable_user_mfa(1, MagicMock())

    @patch("modules.auth.mfa.service.users_integration.require_user")
    def test_mfa_not_enabled(self, mock_get_user):
        mock_user = MagicMock()
        mock_user.mfa_enabled = False
        mock_get_user.return_value = mock_user

        with (
            patch("modules.auth.mfa.service.is_mfa_enabled_for_user", return_value=False),
            pytest.raises(core_exceptions.InvalidInputError),
        ):
            mfa_service.disable_user_mfa(1, MagicMock())


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
            user = mfa_service.users_integration.require_user.return_value
            return getattr(user, "auth_mfa", None)

        with patch("modules.auth.mfa.service.auth_mfa_crud.get_user_mfa_row", side_effect=_row):
            yield

    @patch("modules.auth.mfa.service.mfa_totp_replay_store.matching_totp_step")
    @patch("modules.auth.mfa.service.core_cryptography.decrypt_token_fernet")
    @patch("modules.auth.mfa.service.users_integration.require_user")
    def test_totp_verification_success(self, mock_get_user, mock_decrypt, mock_verify):
        mock_user = MagicMock()
        mock_user.auth_mfa.mfa_enabled = True
        mock_user.auth_mfa.mfa_secret = "encrypted_secret"
        mock_get_user.return_value = mock_user
        mock_decrypt.return_value = "decrypted_secret"
        mock_verify.return_value = 7

        result = mfa_service.verify_user_mfa(1, "123456", MagicMock(), MagicMock(), replay_guard=MagicMock())
        assert result is True
        mock_decrypt.assert_called_once_with("encrypted_secret")
        assert mock_verify.call_args.args[:2] == ("decrypted_secret", "123456")

    @patch("modules.auth.mfa.service.mfa_totp_replay_store.matching_totp_step")
    @patch("modules.auth.mfa.service.core_cryptography.decrypt_token_fernet")
    @patch("modules.auth.mfa.service.users_integration.require_user")
    def test_totp_verify_value_error_returns_false(self, mock_get_user, mock_decrypt, mock_verify):
        mock_user = MagicMock()
        mock_user.auth_mfa.mfa_enabled = True
        mock_user.auth_mfa.mfa_secret = "encrypted_secret"
        mock_get_user.return_value = mock_user
        mock_decrypt.return_value = "decrypted_secret"
        mock_verify.side_effect = ValueError("invalid token")

        result = mfa_service.verify_user_mfa(1, "123456", MagicMock(), MagicMock(), replay_guard=MagicMock())
        assert result is False

    @patch("modules.auth.mfa.service.mfa_totp_replay_store.matching_totp_step")
    @patch("modules.auth.mfa.service.core_cryptography.decrypt_token_fernet")
    @patch("modules.auth.mfa.service.users_integration.require_user")
    def test_totp_verify_unexpected_exception_propagates(self, mock_get_user, mock_decrypt, mock_verify):
        """Unexpected non-OTP errors bubble up instead of being swallowed as False."""
        mock_user = MagicMock()
        mock_user.auth_mfa.mfa_enabled = True
        mock_user.auth_mfa.mfa_secret = "encrypted_secret"
        mock_get_user.return_value = mock_user
        mock_decrypt.return_value = "decrypted_secret"
        mock_verify.side_effect = RuntimeError("unexpected infrastructure error")

        with pytest.raises(RuntimeError, match="unexpected infrastructure error"):
            mfa_service.verify_user_mfa(1, "123456", MagicMock(), MagicMock(), replay_guard=MagicMock())

    @patch("modules.auth.mfa.service.users_integration.require_user")
    def test_user_not_found(self, mock_get_user):
        mock_get_user.side_effect = core_exceptions.NotFoundError("User not found")

        with pytest.raises(core_exceptions.NotFoundError):
            mfa_service.verify_user_mfa(1, "123456", MagicMock(), MagicMock(), replay_guard=MagicMock())

    @patch("modules.auth.mfa.service.users_integration.require_user")
    def test_mfa_not_enabled_returns_false(self, mock_get_user):
        mock_user = MagicMock()
        mock_user.auth_mfa = None
        mock_get_user.return_value = mock_user

        result = mfa_service.verify_user_mfa(1, "123456", MagicMock(), MagicMock(), replay_guard=MagicMock())
        assert result is False

    @patch("modules.auth.mfa.service.users_integration.require_user")
    def test_mfa_disabled_returns_false(self, mock_get_user):
        mock_user = MagicMock()
        mock_user.auth_mfa.mfa_enabled = False
        mock_get_user.return_value = mock_user

        result = mfa_service.verify_user_mfa(1, "123456", MagicMock(), MagicMock(), replay_guard=MagicMock())
        assert result is False

    @patch("modules.auth.mfa.service.users_integration.require_user")
    def test_mfa_no_secret_returns_false(self, mock_get_user):
        mock_user = MagicMock()
        mock_user.auth_mfa.mfa_enabled = True
        mock_user.auth_mfa.mfa_secret = None
        mock_get_user.return_value = mock_user

        result = mfa_service.verify_user_mfa(1, "123456", MagicMock(), MagicMock(), replay_guard=MagicMock())
        assert result is False

    @patch("modules.auth.mfa.service.core_cryptography.decrypt_token_fernet")
    @patch("modules.auth.mfa.service.users_integration.require_user")
    def test_totp_decrypt_failure_returns_false(self, mock_get_user, mock_decrypt):
        mock_user = MagicMock()
        mock_user.auth_mfa.mfa_enabled = True
        mock_user.auth_mfa.mfa_secret = "encrypted_secret"
        mock_get_user.return_value = mock_user
        mock_decrypt.return_value = None

        result = mfa_service.verify_user_mfa(1, "123456", MagicMock(), MagicMock(), replay_guard=MagicMock())
        assert result is False

    @patch("modules.auth.mfa.service.mfa_totp_replay_store.matching_totp_step")
    @patch("modules.auth.mfa.service.core_cryptography.decrypt_token_fernet")
    @patch("modules.auth.mfa.service.users_integration.require_user")
    def test_backup_code_verification_success(self, mock_get_user, mock_decrypt, mock_verify):
        mock_user = MagicMock()
        mock_user.auth_mfa.mfa_enabled = True
        mock_user.auth_mfa.mfa_secret = "encrypted_secret"
        mock_get_user.return_value = mock_user
        mock_verify.return_value = None

        mock_password_verifier = MagicMock()

        with patch(
            "modules.auth.mfa.service.mfa_backup_codes_integration.verify_and_consume_backup_code", return_value=True
        ) as mock_backup:
            result = mfa_service.verify_user_mfa(
                1, "ABCD-EFGH", mock_password_verifier, MagicMock(), replay_guard=MagicMock()
            )
            assert result is True
            mock_backup.assert_called_once_with(1, "ABCD-EFGH", mock_password_verifier, mock_backup.call_args[0][3])

    @patch("modules.auth.mfa.service.mfa_totp_replay_store.matching_totp_step")
    @patch("modules.auth.mfa.service.core_cryptography.decrypt_token_fernet")
    @patch("modules.auth.mfa.service.users_integration.require_user")
    def test_backup_code_verification_failure_returns_false(self, mock_get_user, mock_decrypt, mock_verify):
        mock_user = MagicMock()
        mock_user.auth_mfa.mfa_enabled = True
        mock_user.auth_mfa.mfa_secret = "encrypted_secret"
        mock_get_user.return_value = mock_user
        mock_verify.return_value = None

        mock_password_verifier = MagicMock()

        with patch(
            "modules.auth.mfa.service.mfa_backup_codes_integration.verify_and_consume_backup_code", return_value=False
        ):
            result = mfa_service.verify_user_mfa(
                1, "ABCD-EFGH", mock_password_verifier, MagicMock(), replay_guard=MagicMock()
            )
            assert result is False

    @patch("modules.auth.mfa.service.users_integration.require_user")
    def test_invalid_code_format_returns_false(self, mock_get_user):
        mock_user = MagicMock()
        mock_user.auth_mfa.mfa_enabled = True
        mock_user.auth_mfa.mfa_secret = "encrypted_secret"
        mock_get_user.return_value = mock_user

        result = mfa_service.verify_user_mfa(1, "invalid", MagicMock(), MagicMock(), replay_guard=MagicMock())
        assert result is False

    @patch("modules.auth.mfa.service.mfa_totp_replay_store.matching_totp_step")
    @patch("modules.auth.mfa.service.core_cryptography.decrypt_token_fernet")
    @patch("modules.auth.mfa.service.users_integration.require_user")
    def test_backup_code_unexpected_exception_propagates(self, mock_get_user, mock_decrypt, mock_verify):
        """Unexpected errors from backup-code verification propagate to the global handler.

        Backup-code verification does not swallow unexpected exceptions; only
        legitimate False returns map to a failed check.
        """
        mock_user = MagicMock()
        mock_user.auth_mfa.mfa_enabled = True
        mock_user.auth_mfa.mfa_secret = "encrypted_secret"
        mock_get_user.return_value = mock_user
        mock_verify.return_value = None

        mock_password_verifier = MagicMock()

        with (
            patch(
                "modules.auth.mfa.service.mfa_backup_codes_integration.verify_and_consume_backup_code",
                side_effect=RuntimeError("storage failure"),
            ),
            pytest.raises(RuntimeError, match="storage failure"),
        ):
            mfa_service.verify_user_mfa(1, "ABCD-EFGH", mock_password_verifier, MagicMock(), replay_guard=MagicMock())


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
            user = mfa_service.users_integration.require_user.return_value
            return getattr(user, "auth_mfa", None)

        with patch("modules.auth.mfa.service.auth_mfa_crud.get_user_mfa_row", side_effect=_row):
            yield

    @patch("modules.auth.mfa.service.users_integration.require_user")
    def test_mfa_enabled(self, mock_get_user):
        mock_user = MagicMock()
        mock_user.auth_mfa.mfa_enabled = True
        mock_user.auth_mfa.mfa_secret = "secret"
        mock_get_user.return_value = mock_user

        result = mfa_service.is_mfa_enabled_for_user(1, MagicMock())
        assert result is True

    @patch("modules.auth.mfa.service.users_integration.require_user")
    def test_user_not_found_returns_false(self, mock_get_user):
        mock_get_user.side_effect = core_exceptions.NotFoundError("User not found")

        result = mfa_service.is_mfa_enabled_for_user(1, MagicMock())
        assert result is False

    @patch("modules.auth.mfa.service.users_integration.require_user")
    def test_mfa_not_enabled_returns_false(self, mock_get_user):
        mock_user = MagicMock()
        mock_user.auth_mfa = None
        mock_get_user.return_value = mock_user

        result = mfa_service.is_mfa_enabled_for_user(1, MagicMock())
        assert result is False

    @patch("modules.auth.mfa.service.users_integration.require_user")
    def test_mfa_disabled_returns_false(self, mock_get_user):
        mock_user = MagicMock()
        mock_user.auth_mfa.mfa_enabled = False
        mock_get_user.return_value = mock_user

        result = mfa_service.is_mfa_enabled_for_user(1, MagicMock())
        assert result is False

    @patch("modules.auth.mfa.service.users_integration.require_user")
    def test_mfa_no_secret_returns_false(self, mock_get_user):
        mock_user = MagicMock()
        mock_user.auth_mfa.mfa_enabled = True
        mock_user.auth_mfa.mfa_secret = None
        mock_get_user.return_value = mock_user

        result = mfa_service.is_mfa_enabled_for_user(1, MagicMock())
        assert result is False
