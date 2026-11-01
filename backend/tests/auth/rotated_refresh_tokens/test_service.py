from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock, patch

import pytest

import modules.auth.rotated_refresh_tokens.models as rotated_token_models
import modules.auth.rotated_refresh_tokens.scheduled_jobs as rotated_token_jobs
import modules.auth.rotated_refresh_tokens.service as rotated_token_utils


class TestHmacHashToken:
    """Tests for keyed hashing of refresh tokens."""

    def test_hmac_hash_token_success(self):
        with patch("modules.auth.access_tokens.service.JWT_SECRET_KEY", "test-secret-key"):
            result = rotated_token_utils.hmac_hash_token("test-refresh-token")
        assert isinstance(result, str)
        assert len(result) == 64

    def test_hmac_hash_token_deterministic(self):
        with patch("modules.auth.access_tokens.service.JWT_SECRET_KEY", "test-secret-key"):
            result1 = rotated_token_utils.hmac_hash_token("test-refresh-token")
            result2 = rotated_token_utils.hmac_hash_token("test-refresh-token")
        assert result1 == result2

    def test_hmac_hash_token_different_tokens(self):
        with patch("modules.auth.access_tokens.service.JWT_SECRET_KEY", "test-secret-key"):
            hash1 = rotated_token_utils.hmac_hash_token("token-one")
            hash2 = rotated_token_utils.hmac_hash_token("token-two")
        assert hash1 != hash2

    def test_hmac_hash_token_no_secret(self):
        with (
            patch("modules.auth.access_tokens.service.JWT_SECRET_KEY", None),
            pytest.raises(ValueError, match="JWT_SECRET_KEY"),
        ):
            rotated_token_utils.hmac_hash_token("test-refresh-token")


class TestStoreRotatedToken:
    """
    Test suite for store_rotated_token function.
    """

    @patch("modules.auth.rotated_refresh_tokens.service.core_cryptography")
    @patch("modules.auth.rotated_refresh_tokens.service.rotated_token_crud")
    @patch("modules.auth.rotated_refresh_tokens.service.hmac_hash_token")
    def test_store_rotated_token_success(self, mock_hash, mock_crud, mock_crypto):
        """
        Test successful storage of rotated token.
        """
        # Arrange
        mock_hash.return_value = "hashed-token"
        mock_crypto.encrypt_token_fernet.return_value = "encrypted-replacement"
        replacement_exp = datetime.now(UTC) + timedelta(days=7)
        rotated_exp = datetime.now(UTC) + timedelta(days=6)
        mock_db = MagicMock()

        # Act
        rotated_token_utils.store_rotated_token(
            "raw-token",
            "family-id",
            0,
            mock_db,
            refresh_token_exp=rotated_exp,
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
        assert stored_schema.refresh_token_exp == rotated_exp


class TestCheckTokenReuse:
    """
    Test suite for check_token_reuse function.
    """

    @patch("modules.auth.rotated_refresh_tokens.service.rotated_token_crud")
    @patch("modules.auth.rotated_refresh_tokens.service.hmac_hash_token")
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

    @patch("modules.auth.rotated_refresh_tokens.service.rotated_token_crud")
    @patch("modules.auth.rotated_refresh_tokens.service.hmac_hash_token")
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

    @patch("modules.auth.rotated_refresh_tokens.service.rotated_token_crud")
    @patch("modules.auth.rotated_refresh_tokens.service.hmac_hash_token")
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

    @patch("modules.auth.rotated_refresh_tokens.service.core_cryptography")
    @patch("modules.auth.rotated_refresh_tokens.service.rotated_token_crud")
    @patch("modules.auth.rotated_refresh_tokens.service.hmac_hash_token")
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

    @patch("modules.auth.rotated_refresh_tokens.service.rotated_token_crud")
    @patch("modules.auth.rotated_refresh_tokens.service.hmac_hash_token")
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

    @patch("modules.auth.rotated_refresh_tokens.service.rotated_token_crud")
    @patch("modules.auth.rotated_refresh_tokens.service.hmac_hash_token")
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

    @patch("modules.auth.rotated_refresh_tokens.service.rotated_token_crud")
    @patch("modules.auth.rotated_refresh_tokens.service.hmac_hash_token")
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


class TestDeleteTokenFamily:
    """Tests for staging deletion of rotated records in a family."""

    @patch("modules.auth.rotated_refresh_tokens.service.rotated_token_crud.delete_by_family", return_value=5)
    def test_delete_by_family_stages_records(self, mock_delete, mock_db):
        assert rotated_token_utils.delete_by_family("family-id", mock_db) == 5
        mock_delete.assert_called_once_with("family-id", mock_db)


class TestCleanupExpiredRotatedTokens:
    """Tests for rotated-token cleanup scheduling."""

    @patch("modules.auth.rotated_refresh_tokens.scheduled_jobs.core_database.SessionLocal")
    @patch("modules.auth.rotated_refresh_tokens.scheduled_jobs.rotated_token_service.delete_expired_tokens")
    def test_cleanup_hands_its_session_to_the_purge(self, mock_delete, mock_session_local):
        """The purge commits one batch at a time, so the job only opens the session."""
        db = MagicMock()
        mock_session_local.return_value.__enter__.return_value = db
        mock_delete.return_value = 10
        rotated_token_jobs.delete_expired_rotated_tokens()
        assert mock_delete.call_args.args[1] is db
        db.commit.assert_not_called()

    @patch("modules.auth.rotated_refresh_tokens.scheduled_jobs.core_database.SessionLocal")
    @patch("modules.auth.rotated_refresh_tokens.scheduled_jobs.rotated_token_service.delete_expired_tokens")
    def test_cleanup_removes_what_has_expired_by_now(self, mock_delete, mock_session_local):
        """Each record carries its own token's expiry, so the job asks only for what has passed."""
        mock_session_local.return_value.__enter__.return_value = MagicMock()
        mock_delete.return_value = 0
        before = datetime.now(UTC)
        rotated_token_jobs.delete_expired_rotated_tokens()
        assert before <= mock_delete.call_args.args[0] <= datetime.now(UTC)

    def test_recurring_job_runs_every_minute(self):
        assert rotated_token_jobs.recurring_jobs()[0].minutes == 1


class TestTokenReuseGracePeriod:
    """
    Test suite for TOKEN_REUSE_GRACE_PERIOD_SECONDS constant.
    """

    def test_grace_period_value(self):
        """
        Test grace period is 10 seconds.
        """
        # Assert
        assert rotated_token_utils.TOKEN_REUSE_GRACE_PERIOD_SECONDS == 10


class _FixedClock:
    """Stand-in for the service's ``datetime`` whose ``now`` returns a settable instant."""

    current = datetime(2026, 1, 1, 12, 0, 0, tzinfo=UTC)

    @classmethod
    def now(cls, tz=None):
        return cls.current


class TestGraceWindowTiming:
    """
    Test suite for the replay grace window measured from the rotation instant.
    """

    ROTATED_AT = datetime(2026, 1, 1, 12, 0, 0, tzinfo=UTC)

    def _rotate_and_present(self, seconds_after: int, mock_hash, mock_crud, mock_crypto):
        """Store a rotation at ROTATED_AT, then present the token ``seconds_after`` later.

        Returns:
            The stored schema, and the record the lookup returns for the replay.
        """
        mock_hash.return_value = "hashed-token"
        mock_crypto.encrypt_token_fernet.return_value = "encrypted-replacement"
        mock_crypto.decrypt_token_fernet.return_value = "decrypted-replacement"
        replacement_exp = self.ROTATED_AT + timedelta(days=7)
        _FixedClock.current = self.ROTATED_AT
        rotated_token_utils.store_rotated_token(
            "raw-token",
            "family-id",
            0,
            MagicMock(),
            refresh_token_exp=self.ROTATED_AT + timedelta(days=6),
            replacement_refresh_token="new-refresh-token",
            replacement_refresh_token_exp=replacement_exp,
        )
        stored = mock_crud.create_rotated_token.call_args.args[0]
        record = MagicMock(spec=rotated_token_models.RotatedRefreshToken)
        record.expires_at = stored.expires_at
        record.rotated_at = stored.rotated_at
        record.token_family_id = "family-id"
        record.rotation_count = 0
        record.replacement_refresh_token = "encrypted-replacement"
        record.replacement_refresh_token_exp = replacement_exp
        mock_crud.get_rotated_token_by_hash.return_value = record
        _FixedClock.current = self.ROTATED_AT + timedelta(seconds=seconds_after)
        return stored

    @patch("modules.auth.rotated_refresh_tokens.service.datetime", _FixedClock)
    @patch("modules.auth.rotated_refresh_tokens.service.core_cryptography")
    @patch("modules.auth.rotated_refresh_tokens.service.rotated_token_crud")
    @patch("modules.auth.rotated_refresh_tokens.service.hmac_hash_token")
    def test_store_rotated_token_expires_ten_seconds_after_rotation(self, mock_hash, mock_crud, mock_crypto):
        stored = self._rotate_and_present(0, mock_hash, mock_crud, mock_crypto)

        assert stored.expires_at == stored.rotated_at + timedelta(seconds=10)

    @patch("modules.auth.rotated_refresh_tokens.service.datetime", _FixedClock)
    @patch("modules.auth.rotated_refresh_tokens.service.core_cryptography")
    @patch("modules.auth.rotated_refresh_tokens.service.rotated_token_crud")
    @patch("modules.auth.rotated_refresh_tokens.service.hmac_hash_token")
    def test_token_presented_11_seconds_after_rotation_is_theft(self, mock_hash, mock_crud, mock_crypto):
        self._rotate_and_present(11, mock_hash, mock_crud, mock_crypto)

        assert rotated_token_utils.check_token_reuse("raw-token", MagicMock()) == (True, False)
        assert rotated_token_utils.get_grace_replay_token("raw-token", MagicMock()) is None

    @patch("modules.auth.rotated_refresh_tokens.service.datetime", _FixedClock)
    @patch("modules.auth.rotated_refresh_tokens.service.core_cryptography")
    @patch("modules.auth.rotated_refresh_tokens.service.rotated_token_crud")
    @patch("modules.auth.rotated_refresh_tokens.service.hmac_hash_token")
    def test_token_presented_9_seconds_after_rotation_is_in_grace(self, mock_hash, mock_crud, mock_crypto):
        self._rotate_and_present(9, mock_hash, mock_crud, mock_crypto)

        assert rotated_token_utils.check_token_reuse("raw-token", MagicMock()) == (True, True)
        replay = rotated_token_utils.get_grace_replay_token("raw-token", MagicMock())
        assert replay is not None
        assert replay[0] == "decrypted-replacement"
