from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock, patch

import pytest

import modules.auth.sessions.rotated_refresh_tokens.models as rotated_token_models
import modules.auth.sessions.rotated_refresh_tokens.utils as rotated_token_utils


class TestHmacHashToken:
    """
    Test suite for hmac_hash_token function.
    """

    @patch("modules.auth.token_hashing.auth_constants")
    def test_hmac_hash_token_success(self, mock_auth_constants):
        """
        Test successful HMAC hashing of token.
        """
        # Arrange
        mock_auth_constants.JWT_SECRET_KEY = "test-secret-key"
        raw_token = "test-refresh-token"

        # Act
        result = rotated_token_utils.hmac_hash_token(raw_token)

        # Assert
        assert isinstance(result, str)
        assert len(result) == 64  # SHA256 hex output

    @patch("modules.auth.token_hashing.auth_constants")
    def test_hmac_hash_token_deterministic(self, mock_auth_constants):
        """
        Test HMAC hash is deterministic (same input = same output).
        """
        # Arrange
        mock_auth_constants.JWT_SECRET_KEY = "test-secret-key"
        raw_token = "test-refresh-token"

        # Act
        result1 = rotated_token_utils.hmac_hash_token(raw_token)
        result2 = rotated_token_utils.hmac_hash_token(raw_token)

        # Assert
        assert result1 == result2

    @patch("modules.auth.token_hashing.auth_constants")
    def test_hmac_hash_token_different_tokens(self, mock_auth_constants):
        """
        Test different tokens produce different hashes.
        """
        # Arrange
        mock_auth_constants.JWT_SECRET_KEY = "test-secret-key"
        token1 = "token-one"
        token2 = "token-two"

        # Act
        hash1 = rotated_token_utils.hmac_hash_token(token1)
        hash2 = rotated_token_utils.hmac_hash_token(token2)

        # Assert
        assert hash1 != hash2

    @patch("modules.auth.token_hashing.auth_constants")
    def test_hmac_hash_token_no_secret(self, mock_auth_constants):
        """
        Test error when JWT_SECRET_KEY not configured.
        """
        # Arrange
        mock_auth_constants.JWT_SECRET_KEY = None
        raw_token = "test-refresh-token"

        # Act & Assert
        with pytest.raises(ValueError) as exc_info:
            rotated_token_utils.hmac_hash_token(raw_token)

        assert "JWT_SECRET_KEY" in str(exc_info.value)


class TestStoreRotatedToken:
    """
    Test suite for store_rotated_token function.
    """

    @patch("modules.auth.sessions.rotated_refresh_tokens.utils.core_cryptography")
    @patch("modules.auth.sessions.rotated_refresh_tokens.utils.rotated_token_crud")
    @patch("modules.auth.sessions.rotated_refresh_tokens.utils.hmac_hash_token")
    def test_store_rotated_token_success(self, mock_hash, mock_crud, mock_crypto):
        """
        Test successful storage of rotated token.
        """
        # Arrange
        mock_hash.return_value = "hashed-token"
        mock_crypto.encrypt_token_fernet.return_value = "encrypted-replacement"
        replacement_exp = datetime.now(UTC) + timedelta(days=7)
        mock_db = MagicMock()

        # Act
        rotated_token_utils.store_rotated_token(
            "raw-token",
            "family-id",
            0,
            mock_db,
            replacement_refresh_token="new-refresh-token",
            replacement_refresh_token_exp=replacement_exp,
        )

        # Assert
        mock_hash.assert_called_once_with("raw-token")
        mock_crypto.encrypt_token_fernet.assert_called_once_with("new-refresh-token")
        mock_crud.create_rotated_token.assert_called_once()
        stored_schema = mock_crud.create_rotated_token.call_args.args[0]
        assert stored_schema.replacement_refresh_token == "encrypted-replacement"
        assert stored_schema.replacement_refresh_token_exp == replacement_exp


class TestCheckTokenReuse:
    """
    Test suite for check_token_reuse function.
    """

    @patch("modules.auth.sessions.rotated_refresh_tokens.utils.rotated_token_crud")
    @patch("modules.auth.sessions.rotated_refresh_tokens.utils.hmac_hash_token")
    def test_check_token_reuse_not_reused(self, mock_hash, mock_crud):
        """
        Test token that hasn't been rotated.
        """
        # Arrange
        mock_hash.return_value = "hashed-token"
        mock_crud.get_rotated_token_by_hash.return_value = None
        mock_db = MagicMock()

        # Act
        is_reused, in_grace = rotated_token_utils.check_token_reuse("raw-token", mock_db)

        # Assert
        assert is_reused is False
        assert in_grace is False

    @patch("modules.auth.sessions.rotated_refresh_tokens.utils.rotated_token_crud")
    @patch("modules.auth.sessions.rotated_refresh_tokens.utils.hmac_hash_token")
    def test_check_token_reuse_within_grace_period(self, mock_hash, mock_crud):
        """
        Test token reused within grace period.
        """
        # Arrange
        mock_hash.return_value = "hashed-token"
        now = datetime.now(UTC)
        mock_rotated_token = MagicMock(spec=rotated_token_models.RotatedRefreshToken)
        mock_rotated_token.expires_at = now + timedelta(seconds=30)
        mock_rotated_token.token_family_id = "family-id"
        mock_rotated_token.rotation_count = 1
        mock_crud.get_rotated_token_by_hash.return_value = mock_rotated_token
        mock_db = MagicMock()

        # Act
        is_reused, in_grace = rotated_token_utils.check_token_reuse("raw-token", mock_db)

        # Assert
        assert is_reused is True
        assert in_grace is True

    @patch("modules.auth.sessions.rotated_refresh_tokens.utils.rotated_token_crud")
    @patch("modules.auth.sessions.rotated_refresh_tokens.utils.hmac_hash_token")
    def test_check_token_reuse_after_grace_period(self, mock_hash, mock_crud):
        """
        Test token reused after grace period (theft detected).
        """
        # Arrange
        mock_hash.return_value = "hashed-token"
        now = datetime.now(UTC)
        mock_rotated_token = MagicMock(spec=rotated_token_models.RotatedRefreshToken)
        mock_rotated_token.expires_at = now - timedelta(seconds=30)
        mock_rotated_token.token_family_id = "family-id"
        mock_rotated_token.rotation_count = 1
        mock_rotated_token.rotated_at = now - timedelta(seconds=90)
        mock_crud.get_rotated_token_by_hash.return_value = mock_rotated_token
        mock_db = MagicMock()

        # Act
        is_reused, in_grace = rotated_token_utils.check_token_reuse("raw-token", mock_db)

        # Assert
        assert is_reused is True
        assert in_grace is False


class TestGetGraceReplayToken:
    """
    Test suite for get_grace_replay_token function.
    """

    @patch("modules.auth.sessions.rotated_refresh_tokens.utils.core_cryptography")
    @patch("modules.auth.sessions.rotated_refresh_tokens.utils.rotated_token_crud")
    @patch("modules.auth.sessions.rotated_refresh_tokens.utils.hmac_hash_token")
    def test_get_grace_replay_token_success(self, mock_hash, mock_crud, mock_crypto):
        """
        Test replacement returned for an in-grace token.
        """
        # Arrange
        mock_hash.return_value = "hashed-token"
        now = datetime.now(UTC)
        replacement_exp = now + timedelta(days=7)
        mock_rotated_token = MagicMock(spec=rotated_token_models.RotatedRefreshToken)
        mock_rotated_token.expires_at = now + timedelta(seconds=30)
        mock_rotated_token.replacement_refresh_token = "encrypted-replacement"
        mock_rotated_token.replacement_refresh_token_exp = replacement_exp
        mock_crud.get_rotated_token_by_hash.return_value = mock_rotated_token
        mock_crypto.decrypt_token_fernet.return_value = "decrypted-replacement"
        mock_db = MagicMock()

        # Act
        result = rotated_token_utils.get_grace_replay_token("raw-token", mock_db)

        # Assert
        assert result == ("decrypted-replacement", replacement_exp)
        mock_crypto.decrypt_token_fernet.assert_called_once_with("encrypted-replacement")

    @patch("modules.auth.sessions.rotated_refresh_tokens.utils.rotated_token_crud")
    @patch("modules.auth.sessions.rotated_refresh_tokens.utils.hmac_hash_token")
    def test_get_grace_replay_token_no_record(self, mock_hash, mock_crud):
        """
        Test None returned when no rotated record exists.
        """
        # Arrange
        mock_hash.return_value = "hashed-token"
        mock_crud.get_rotated_token_by_hash.return_value = None
        mock_db = MagicMock()

        # Act
        result = rotated_token_utils.get_grace_replay_token("raw-token", mock_db)

        # Assert
        assert result is None

    @patch("modules.auth.sessions.rotated_refresh_tokens.utils.rotated_token_crud")
    @patch("modules.auth.sessions.rotated_refresh_tokens.utils.hmac_hash_token")
    def test_get_grace_replay_token_past_expiry(self, mock_hash, mock_crud):
        """
        Test None returned when the record is past its grace window.
        """
        # Arrange
        mock_hash.return_value = "hashed-token"
        now = datetime.now(UTC)
        mock_rotated_token = MagicMock(spec=rotated_token_models.RotatedRefreshToken)
        mock_rotated_token.expires_at = now - timedelta(seconds=5)
        mock_rotated_token.replacement_refresh_token = "encrypted-replacement"
        mock_rotated_token.replacement_refresh_token_exp = now + timedelta(days=7)
        mock_crud.get_rotated_token_by_hash.return_value = mock_rotated_token
        mock_db = MagicMock()

        # Act
        result = rotated_token_utils.get_grace_replay_token("raw-token", mock_db)

        # Assert
        assert result is None

    @patch("modules.auth.sessions.rotated_refresh_tokens.utils.rotated_token_crud")
    @patch("modules.auth.sessions.rotated_refresh_tokens.utils.hmac_hash_token")
    def test_get_grace_replay_token_no_replacement_stored(self, mock_hash, mock_crud):
        """
        Test None returned when no replacement was stored.
        """
        # Arrange
        mock_hash.return_value = "hashed-token"
        now = datetime.now(UTC)
        mock_rotated_token = MagicMock(spec=rotated_token_models.RotatedRefreshToken)
        mock_rotated_token.expires_at = now + timedelta(seconds=30)
        mock_rotated_token.replacement_refresh_token = None
        mock_rotated_token.replacement_refresh_token_exp = None
        mock_crud.get_rotated_token_by_hash.return_value = mock_rotated_token
        mock_db = MagicMock()

        # Act
        result = rotated_token_utils.get_grace_replay_token("raw-token", mock_db)

        # Assert
        assert result is None


class TestInvalidateTokenFamily:
    """
    Test suite for invalidate_token_family function.
    """

    @patch("modules.auth.sessions.rotated_refresh_tokens.utils.rotated_token_crud")
    @patch("modules.auth.sessions.rotated_refresh_tokens.utils.auth_sessions_crud")
    def test_invalidate_token_family_success(self, mock_session_crud, mock_token_crud):
        """
        Test successful family invalidation.
        """
        # Arrange
        mock_session_crud.delete_sessions_by_family.return_value = 2
        mock_token_crud.delete_by_family.return_value = 5
        mock_db = MagicMock()

        # Act
        result = rotated_token_utils.invalidate_token_family("family-id", mock_db)

        # Assert
        assert result == 2
        mock_session_crud.delete_sessions_by_family.assert_called_once_with("family-id", mock_db)
        mock_token_crud.delete_by_family.assert_called_once_with("family-id", mock_db)


class TestCleanupExpiredRotatedTokens:
    """
    Test suite for cleanup_expired_rotated_tokens function.
    """

    @patch("modules.auth.sessions.rotated_refresh_tokens.utils.SessionLocal")
    @patch("modules.auth.sessions.rotated_refresh_tokens.utils.rotated_token_crud")
    def test_cleanup_expired_rotated_tokens_success(self, mock_crud, mock_session_local):
        """
        Test successful cleanup of expired tokens.
        """
        # Arrange
        mock_db = MagicMock()
        mock_session_local.return_value.__enter__.return_value = mock_db
        mock_crud.delete_expired_tokens.return_value = 10

        # Act
        rotated_token_utils.cleanup_expired_rotated_tokens()

        # Assert
        mock_crud.delete_expired_tokens.assert_called_once()

    @patch("modules.auth.sessions.rotated_refresh_tokens.utils.SessionLocal")
    @patch("modules.auth.sessions.rotated_refresh_tokens.utils.rotated_token_crud")
    def test_cleanup_retains_buffer_past_expiry(self, mock_crud, mock_session_local):
        """
        Test cleanup cutoff is held a buffer behind the current time.
        """
        # Arrange
        mock_db = MagicMock()
        mock_session_local.return_value.__enter__.return_value = mock_db
        mock_crud.delete_expired_tokens.return_value = 0
        buffer = timedelta(seconds=rotated_token_utils.ROTATED_TOKEN_CLEANUP_BUFFER_SECONDS)
        before = datetime.now(UTC)

        # Act
        rotated_token_utils.cleanup_expired_rotated_tokens()
        after = datetime.now(UTC)

        # Assert
        cutoff = mock_crud.delete_expired_tokens.call_args.args[0]
        assert before - buffer <= cutoff <= after - buffer

    @patch("modules.auth.sessions.rotated_refresh_tokens.utils.SessionLocal")
    @patch("modules.auth.sessions.rotated_refresh_tokens.utils.rotated_token_crud")
    @patch("modules.auth.sessions.rotated_refresh_tokens.utils.logger")
    def test_cleanup_expired_rotated_tokens_error_handling(self, mock_logger, mock_crud, mock_session_local):
        """
        Test error handling in cleanup.
        """
        # Arrange
        mock_db = MagicMock()
        mock_session_local.return_value.__enter__.return_value = mock_db
        mock_crud.delete_expired_tokens.side_effect = Exception("Database error")

        # Act (should not raise)
        rotated_token_utils.cleanup_expired_rotated_tokens()

        # Assert
        mock_logger.error.assert_called()


class TestTokenReuseGracePeriod:
    """
    Test suite for TOKEN_REUSE_GRACE_PERIOD_SECONDS constant.
    """

    def test_grace_period_value(self):
        """
        Test grace period is 60 seconds.
        """
        # Assert
        assert rotated_token_utils.TOKEN_REUSE_GRACE_PERIOD_SECONDS == 60


class TestRotatedTokenCleanupBuffer:
    """
    Test suite for ROTATED_TOKEN_CLEANUP_BUFFER_SECONDS constant.
    """

    def test_cleanup_buffer_value(self):
        """
        Test cleanup buffer is 10 seconds.
        """
        # Assert
        assert rotated_token_utils.ROTATED_TOKEN_CLEANUP_BUFFER_SECONDS == 10
