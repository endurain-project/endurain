from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock, patch

import pytest

import core.hashing as hashing
import core.network as network
import modules.auth.rotated_refresh_tokens.models as rotated_token_models
import modules.auth.rotated_refresh_tokens.scheduled_jobs as rotated_token_jobs
import modules.auth.rotated_refresh_tokens.service as rotated_token_utils

_IP = "203.0.113.7"
_UA = "Endurain/1.0"
_FINGERPRINT = hashing.sha256_hex(f"{_IP}\n{_UA}")


class TestHmacHashToken:
    """Tests for keyed hashing of refresh tokens."""

    def test_hmac_hash_token_success(self):
        with patch(
            "modules.auth.access_tokens.integration_service.core_key_derivation.derive_key", return_value="k" * 64
        ):
            result = rotated_token_utils.hmac_hash_token("test-refresh-token")
        assert isinstance(result, str)
        assert len(result) == 64

    def test_hmac_hash_token_deterministic(self):
        with patch(
            "modules.auth.access_tokens.integration_service.core_key_derivation.derive_key", return_value="k" * 64
        ):
            result1 = rotated_token_utils.hmac_hash_token("test-refresh-token")
            result2 = rotated_token_utils.hmac_hash_token("test-refresh-token")
        assert result1 == result2

    def test_hmac_hash_token_different_tokens(self):
        with patch(
            "modules.auth.access_tokens.integration_service.core_key_derivation.derive_key", return_value="k" * 64
        ):
            hash1 = rotated_token_utils.hmac_hash_token("token-one")
            hash2 = rotated_token_utils.hmac_hash_token("token-two")
        assert hash1 != hash2

    def test_hmac_hash_token_no_secret(self):
        with (
            patch("modules.auth.access_tokens.integration_service.core_key_derivation.derive_key", return_value=None),
            pytest.raises(ValueError, match="SECRET_KEY"),
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
            ip_address=_IP,
            user_agent=_UA,
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
        assert stored_schema.client_fingerprint == _FINGERPRINT


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
        mock_crud.get_rotated_token_by_hashes.return_value = None
        mock_db = MagicMock()

        # Act
        is_reused, in_grace = rotated_token_utils.check_token_reuse(
            "raw-token", mock_db, ip_address=_IP, user_agent=_UA
        )

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
        mock_rotated_token.client_fingerprint = _FINGERPRINT
        mock_rotated_token.token_family_id = "family-id"
        mock_rotated_token.rotation_count = 1
        mock_crud.get_rotated_token_by_hashes.return_value = mock_rotated_token
        mock_db = MagicMock()

        # Act
        is_reused, in_grace = rotated_token_utils.check_token_reuse(
            "raw-token", mock_db, ip_address=_IP, user_agent=_UA
        )

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
        mock_crud.get_rotated_token_by_hashes.return_value = mock_rotated_token
        mock_db = MagicMock()

        # Act
        is_reused, in_grace = rotated_token_utils.check_token_reuse(
            "raw-token", mock_db, ip_address=_IP, user_agent=_UA
        )

        # Assert
        assert is_reused is True
        assert in_grace is False


class TestReuseLogsNoSessionId:
    """A reuse log line names the token family by fingerprint, since the family id is the session id."""

    @pytest.mark.parametrize(
        ("expires_in", "same_client"),
        [(30, True), (30, False), (-30, True)],
        ids=["in grace", "in grace from another client", "after grace"],
    )
    @patch("modules.auth.rotated_refresh_tokens.service.rotated_token_crud")
    @patch("modules.auth.rotated_refresh_tokens.service.hmac_hash_token")
    def test_the_family_id_is_logged_as_a_fingerprint(self, mock_hash, mock_crud, expires_in, same_client, caplog):
        import logging

        family_id = "9f2c1d7e-session-handle-0001"
        now = datetime.now(UTC)
        token = MagicMock(spec=rotated_token_models.RotatedRefreshToken)
        token.expires_at = now + timedelta(seconds=expires_in)
        token.client_fingerprint = _FINGERPRINT if same_client else "another-client"
        token.token_family_id = family_id
        token.rotation_count = 1
        token.rotated_at = now - timedelta(seconds=90)
        mock_crud.get_rotated_token_by_hashes.return_value = token

        with caplog.at_level(logging.DEBUG):
            rotated_token_utils.check_token_reuse("raw-token", MagicMock(), ip_address=_IP, user_agent=_UA)

        assert caplog.records
        for record in caplog.records:
            assert family_id not in record.getMessage()
            assert family_id not in str(record.__dict__)
        assert any(hashing.log_fingerprint(family_id) in str(record.__dict__) for record in caplog.records)


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
        mock_rotated_token.client_fingerprint = _FINGERPRINT
        mock_rotated_token.replacement_refresh_token = "encrypted-replacement"
        mock_rotated_token.replacement_refresh_token_exp = replacement_exp
        mock_crud.get_rotated_token_by_hashes.return_value = mock_rotated_token
        mock_crypto.decrypt_token_fernet.return_value = "decrypted-replacement"
        mock_db = MagicMock()

        # Act
        result = rotated_token_utils.get_grace_replay_token("raw-token", mock_db, ip_address=_IP, user_agent=_UA)

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
        mock_crud.get_rotated_token_by_hashes.return_value = None
        mock_db = MagicMock()

        # Act
        result = rotated_token_utils.get_grace_replay_token("raw-token", mock_db, ip_address=_IP, user_agent=_UA)

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
        mock_crud.get_rotated_token_by_hashes.return_value = mock_rotated_token
        mock_db = MagicMock()

        # Act
        result = rotated_token_utils.get_grace_replay_token("raw-token", mock_db, ip_address=_IP, user_agent=_UA)

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
        mock_rotated_token.client_fingerprint = _FINGERPRINT
        mock_rotated_token.replacement_refresh_token = None
        mock_rotated_token.replacement_refresh_token_exp = None
        mock_crud.get_rotated_token_by_hashes.return_value = mock_rotated_token
        mock_db = MagicMock()

        # Act
        result = rotated_token_utils.get_grace_replay_token("raw-token", mock_db, ip_address=_IP, user_agent=_UA)

        # Assert
        assert result is None


def _record(**overrides):
    values = {
        "expires_at": datetime.now(UTC) + timedelta(seconds=30),
        "token_family_id": "family-id",
        "rotation_count": 1,
        "rotated_at": datetime.now(UTC),
        "client_fingerprint": _FINGERPRINT,
        "replacement_refresh_token": "encrypted-replacement",
        "replacement_refresh_token_exp": datetime.now(UTC) + timedelta(days=7),
    }
    values.update(overrides)
    return MagicMock(spec=rotated_token_models.RotatedRefreshToken, **values)


class TestClientBinding:
    """An in-grace retry is the rotating client's only when its network and User-Agent match."""

    @pytest.fixture(autouse=True)
    def _patched(self):
        with (
            patch("modules.auth.rotated_refresh_tokens.service.rotated_token_crud") as crud,
            patch("modules.auth.rotated_refresh_tokens.service.hmac_hash_token_candidates", return_value=("h",)),
            patch("modules.auth.rotated_refresh_tokens.service.core_cryptography") as crypto,
        ):
            crypto.decrypt_token_fernet.return_value = "decrypted-replacement"
            self.crud = crud
            yield

    def _fingerprint_of(self, ip, ua):
        return hashing.sha256_hex(f"{network.client_network(ip)}\n{ua}")

    def _present(self, ip, ua, *, stored_ip="203.0.113.7", stored_ua="Endurain/1.0"):
        self.crud.get_rotated_token_by_hashes.return_value = _record(
            client_fingerprint=self._fingerprint_of(stored_ip, stored_ua)
        )
        reuse = rotated_token_utils.check_token_reuse("raw", MagicMock(), ip_address=ip, user_agent=ua)
        replay = rotated_token_utils.get_grace_replay_token("raw", MagicMock(), ip_address=ip, user_agent=ua)
        return reuse, replay

    def test_the_same_client_is_in_grace_and_gets_the_replay(self):
        reuse, replay = self._present("203.0.113.7", "Endurain/1.0")

        assert reuse == (True, True)
        assert replay is not None and replay[0] == "decrypted-replacement"

    @pytest.mark.parametrize(
        ("ip", "ua"),
        [
            ("203.0.113.8", "Endurain/1.0"),
            ("203.0.113.7", "Endurain/1.1"),
        ],
    )
    def test_another_ipv4_address_or_user_agent_is_theft(self, ip, ua):
        reuse, replay = self._present(ip, ua)

        assert reuse == (True, False)
        assert replay is None

    def test_another_ipv6_64_is_theft(self):
        reuse, replay = self._present(
            "2001:db8:0:2::1", "Endurain/1.0", stored_ip="2001:db8:0:1::1", stored_ua="Endurain/1.0"
        )

        assert reuse == (True, False)
        assert replay is None

    def test_the_same_ipv6_64_with_another_host_part_matches(self):
        reuse, replay = self._present(
            "2001:db8:0:1::ffff", "Endurain/1.0", stored_ip="2001:db8:0:1::1", stored_ua="Endurain/1.0"
        )

        assert reuse == (True, True)
        assert replay is not None

    def test_a_mismatch_warns_that_the_replay_came_from_another_client(self):
        self.crud.get_rotated_token_by_hashes.return_value = _record()
        with patch("modules.auth.rotated_refresh_tokens.service.logger") as logger:
            rotated_token_utils.check_token_reuse("raw", MagicMock(), ip_address="198.51.100.1", user_agent=_UA)

        assert "another client" in logger.warning.call_args.args[0]


class TestDeleteTokenFamily:
    """Tests for staging deletion of rotated records in a family."""

    @patch("modules.auth.rotated_refresh_tokens.service.rotated_token_crud.delete_by_family", return_value=5)
    def test_delete_by_family_stages_records(self, mock_delete, mock_db):
        assert rotated_token_utils.delete_by_family("family-id", mock_db) == 5
        mock_delete.assert_called_once_with("family-id", mock_db)


class TestCleanupExpiredRotatedTokens:
    """Tests for rotated-token cleanup scheduling."""

    @patch("modules.auth.rotated_refresh_tokens.scheduled_jobs.core_database.SessionLocal")
    @patch("modules.auth.rotated_refresh_tokens.scheduled_jobs.rotated_token_service.clear_expired_replacements")
    @patch("modules.auth.rotated_refresh_tokens.scheduled_jobs.rotated_token_service.delete_expired_tokens")
    def test_cleanup_hands_its_session_to_the_purge(self, mock_delete, mock_clear, mock_session_local):
        """The purge commits one batch at a time, so the job only opens the session."""
        db = MagicMock()
        mock_session_local.return_value.__enter__.return_value = db
        mock_delete.return_value = 10
        rotated_token_jobs.delete_expired_rotated_tokens()
        assert mock_delete.call_args.args[1] is db
        assert mock_clear.call_args.args[1] is db
        db.commit.assert_not_called()

    @patch("modules.auth.rotated_refresh_tokens.scheduled_jobs.core_database.SessionLocal")
    @patch("modules.auth.rotated_refresh_tokens.scheduled_jobs.rotated_token_service.clear_expired_replacements")
    @patch("modules.auth.rotated_refresh_tokens.scheduled_jobs.rotated_token_service.delete_expired_tokens")
    def test_cleanup_removes_what_has_expired_by_now(self, mock_delete, mock_clear, mock_session_local):
        """Each record carries its own token's expiry, so the job asks only for what has passed."""
        mock_session_local.return_value.__enter__.return_value = MagicMock()
        mock_delete.return_value = 0
        before = datetime.now(UTC)
        rotated_token_jobs.delete_expired_rotated_tokens()
        assert before <= mock_delete.call_args.args[0] <= datetime.now(UTC)
        assert before <= mock_clear.call_args.args[0] <= datetime.now(UTC)
        assert mock_clear.call_args.args[0] == mock_delete.call_args.args[0]

    @patch("modules.auth.rotated_refresh_tokens.scheduled_jobs.core_database.SessionLocal")
    @patch("modules.auth.rotated_refresh_tokens.scheduled_jobs.rotated_token_service.clear_expired_replacements")
    @patch("modules.auth.rotated_refresh_tokens.scheduled_jobs.rotated_token_service.delete_expired_tokens")
    def test_cleanup_clears_replacements_before_deleting(self, mock_delete, mock_clear, mock_session_local):
        mock_session_local.return_value.__enter__.return_value = MagicMock()
        mock_clear.return_value = 0
        mock_delete.return_value = 0
        parent = MagicMock()
        parent.attach_mock(mock_clear, "clear")
        parent.attach_mock(mock_delete, "delete")
        rotated_token_jobs.delete_expired_rotated_tokens()
        assert [call[0] for call in parent.mock_calls] == ["clear", "delete"]

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
            ip_address=_IP,
            user_agent=_UA,
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
        record.client_fingerprint = stored.client_fingerprint
        record.replacement_refresh_token = "encrypted-replacement"
        record.replacement_refresh_token_exp = replacement_exp
        mock_crud.get_rotated_token_by_hashes.return_value = record
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

        assert rotated_token_utils.check_token_reuse("raw-token", MagicMock(), ip_address=_IP, user_agent=_UA) == (
            True,
            False,
        )
        assert (
            rotated_token_utils.get_grace_replay_token("raw-token", MagicMock(), ip_address=_IP, user_agent=_UA) is None
        )

    @patch("modules.auth.rotated_refresh_tokens.service.datetime", _FixedClock)
    @patch("modules.auth.rotated_refresh_tokens.service.core_cryptography")
    @patch("modules.auth.rotated_refresh_tokens.service.rotated_token_crud")
    @patch("modules.auth.rotated_refresh_tokens.service.hmac_hash_token")
    def test_token_presented_9_seconds_after_rotation_is_in_grace(self, mock_hash, mock_crud, mock_crypto):
        self._rotate_and_present(9, mock_hash, mock_crud, mock_crypto)

        assert rotated_token_utils.check_token_reuse("raw-token", MagicMock(), ip_address=_IP, user_agent=_UA) == (
            True,
            True,
        )
        replay = rotated_token_utils.get_grace_replay_token("raw-token", MagicMock(), ip_address=_IP, user_agent=_UA)
        assert replay is not None
        assert replay[0] == "decrypted-replacement"


class TestKeyRotation:
    """A token rotated under the old ``SECRET_KEY`` is still recognised once the key list is ``new,old``."""

    _OLD = "o" * 40
    _NEW = "n" * 40

    @staticmethod
    def _with_secret(secret: str):
        import core.key_derivation as core_key_derivation

        core_key_derivation.derive_keys.cache_clear()
        return patch("core.key_derivation.core_config.read_secret", return_value=secret)

    @pytest.fixture(autouse=True)
    def _fresh_keys(self):
        import core.key_derivation as core_key_derivation

        core_key_derivation.derive_keys.cache_clear()
        yield
        core_key_derivation.derive_keys.cache_clear()

    def test_reuse_of_a_token_rotated_under_the_old_key_is_detected(self):
        from tests._helpers.db import create_sqlite_session

        db = create_sqlite_session()
        now = datetime.now(UTC)
        with (
            self._with_secret(self._OLD),
            patch.object(rotated_token_utils.core_cryptography, "encrypt_token_fernet", return_value="x"),
        ):
            rotated_token_utils.store_rotated_token(
                "old-token",
                "f" * 36,
                1,
                db,
                ip_address=_IP,
                user_agent=_UA,
                refresh_token_exp=now + timedelta(days=1),
                replacement_refresh_token="new-token",
                replacement_refresh_token_exp=now + timedelta(days=1),
            )
        crud = rotated_token_utils.rotated_token_crud
        with self._with_secret(f"{self._NEW},{self._OLD}"):
            found = crud.get_rotated_token_by_hashes(rotated_token_utils.hmac_hash_token_candidates("old-token"), db)
        with self._with_secret(self._NEW):
            unseen = crud.get_rotated_token_by_hashes(rotated_token_utils.hmac_hash_token_candidates("old-token"), db)

        assert found is not None
        assert unseen is None
        db.close()

    def test_new_records_are_hashed_with_the_first_key(self):
        with self._with_secret(f"{self._NEW},{self._OLD}"):
            first = rotated_token_utils.hmac_hash_token("t")
            candidates = rotated_token_utils.hmac_hash_token_candidates("t")

        assert candidates[0] == first
        assert len(set(candidates)) == 2


class TestReplayAfterReplacementCleared:
    """A replacement cleared after the grace window must not weaken reuse detection."""

    def test_replay_after_grace_is_still_reuse_and_replays_nothing(self):
        from tests._helpers.db import create_sqlite_session

        db = create_sqlite_session()
        now = datetime.now(UTC)
        with patch.object(rotated_token_utils.core_cryptography, "encrypt_token_fernet", return_value="x"):
            rotated_token_utils.store_rotated_token(
                "old-token",
                "f" * 36,
                1,
                db,
                ip_address=_IP,
                user_agent=_UA,
                refresh_token_exp=now + timedelta(days=1),
                replacement_refresh_token="new-token",
                replacement_refresh_token_exp=now + timedelta(days=1),
            )
        db.query(rotated_token_models.RotatedRefreshToken).update({"expires_at": now - timedelta(seconds=1)})
        db.flush()

        assert rotated_token_utils.clear_expired_replacements(now, db) == 1

        # SQLite returns naive datetimes, so the service's clock is naive here too.
        _FixedClock.current = now.replace(tzinfo=None)
        with patch.object(rotated_token_utils, "datetime", _FixedClock):
            assert rotated_token_utils.check_token_reuse("old-token", db, ip_address=_IP, user_agent=_UA) == (
                True,
                False,
            )
            assert rotated_token_utils.get_grace_replay_token("old-token", db, ip_address=_IP, user_agent=_UA) is None
        db.close()
