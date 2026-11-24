"""A rotated refresh token is remembered: reusing it is theft unless the rotating client retries in the grace window."""

import uuid
from datetime import UTC, datetime, timedelta

import pytest
import sqlalchemy as sa
from sqlalchemy.exc import IntegrityError

import core.database as core_database
import core.exceptions as core_exceptions
import core.key_derivation as core_key_derivation
import modules.auth.rotated_refresh_tokens.crud as rotated_crud
import modules.auth.rotated_refresh_tokens.integration_service as rotated_integration
import modules.auth.rotated_refresh_tokens.models as rotated_models
import modules.auth.rotated_refresh_tokens.scheduled_jobs as rotated_scheduled_jobs
import modules.auth.rotated_refresh_tokens.service as rotated_service
from tests._factories.auth import make_session
from tests._factories.users import make_user

_IP = "203.0.113.7"
_UA = "Endurain/1.0"
_TOKEN = "old-token"


def _rotate(db, token: str = _TOKEN, family: uuid.UUID | None = None, *, ip: str = _IP, ua: str = _UA, exp=None):
    """Store a rotation of ``token`` as a refresh does, with its replacement; return the family id."""
    if family is None:
        family = make_session(db, make_user(db)).token_family_id
    rotated_service.store_rotated_token(
        token,
        family,
        1,
        db,
        ip_address=ip,
        user_agent=ua,
        refresh_token_exp=exp or datetime.now(UTC) + timedelta(days=1),
        replacement_refresh_token="replacement-token",
        replacement_refresh_token_exp=datetime.now(UTC) + timedelta(days=7),
    )
    return family


def _rows(db) -> list[rotated_models.RotatedRefreshToken]:
    return list(db.scalars(sa.select(rotated_models.RotatedRefreshToken)))


def _age(db, seconds: float) -> None:
    """Move every rotation back in time, as if it had happened ``seconds`` ago."""
    shift = timedelta(seconds=seconds)
    db.execute(
        sa.update(rotated_models.RotatedRefreshToken).values(
            rotated_at=rotated_models.RotatedRefreshToken.rotated_at - shift,
            expires_at=rotated_models.RotatedRefreshToken.expires_at - shift,
        )
    )
    db.flush()


@pytest.fixture
def secret_key(monkeypatch):
    """Return a function that makes the server's ``SECRET_KEY`` list the given one, as a rotation does."""

    read_secret = core_key_derivation.core_config.read_secret

    def use(secret: str) -> None:
        core_key_derivation.derive_keys.cache_clear()
        monkeypatch.setattr(
            core_key_derivation.core_config,
            "read_secret",
            lambda name, default_value=None: secret if name == "SECRET_KEY" else read_secret(name, default_value),
        )

    yield use
    core_key_derivation.derive_keys.cache_clear()


class TestHashing:
    def test_a_token_hashes_to_a_stable_hex_digest_that_differs_per_token(self):
        first = rotated_service.hmac_hash_token("token-one")

        assert len(first) == 64
        assert first == rotated_service.hmac_hash_token("token-one")
        assert first != rotated_service.hmac_hash_token("token-two")
        assert "token-one" not in first

    def test_a_server_without_a_secret_key_refuses_to_hash(self, monkeypatch):
        core_key_derivation.derive_keys.cache_clear()
        monkeypatch.setattr(core_key_derivation, "derive_key", lambda *_a, **_k: None)

        with pytest.raises(ValueError, match="SECRET_KEY"):
            rotated_service.hmac_hash_token("token")
        core_key_derivation.derive_keys.cache_clear()


class TestStore:
    def test_a_rotation_stores_the_digest_the_clients_fingerprint_and_the_replacement_encrypted(self, db):
        family = _rotate(db)

        (row,) = _rows(db)
        assert row.token_family_id == family
        assert row.hashed_token == rotated_service.hmac_hash_token(_TOKEN)
        assert _TOKEN not in row.hashed_token
        assert row.replacement_refresh_token not in (None, "replacement-token")
        assert row.client_fingerprint not in (_IP, _UA)
        assert row.rotation_count == 1

    def test_the_grace_window_is_ten_seconds_after_the_rotation(self, db):
        _rotate(db)

        (row,) = _rows(db)
        assert row.expires_at - row.rotated_at == timedelta(seconds=rotated_service.TOKEN_REUSE_GRACE_PERIOD_SECONDS)
        assert rotated_service.TOKEN_REUSE_GRACE_PERIOD_SECONDS == 10

    def test_rotating_the_same_token_twice_is_a_conflict(self, db):
        _rotate(db)

        with pytest.raises(core_exceptions.ConflictError), db.begin_nested():
            _rotate(db)

        assert len(_rows(db)) == 1

    def test_a_record_is_unique_per_digest_in_the_database(self, db):
        _rotate(db)
        values = {c.name: getattr(_rows(db)[0], c.name) for c in rotated_models.RotatedRefreshToken.__table__.columns}

        with pytest.raises(IntegrityError), db.begin_nested():
            db.execute(sa.insert(rotated_models.RotatedRefreshToken).values(**(values | {"id": uuid.uuid4()})))


class TestCheckReuse:
    def test_a_token_never_rotated_is_not_reused(self, db):
        assert rotated_service.check_token_reuse("fresh-token", db, ip_address=_IP, user_agent=_UA) == (False, False)

    def test_the_rotating_client_presenting_it_again_inside_the_grace_window_is_a_retry(self, db):
        _rotate(db)

        assert rotated_service.check_token_reuse(_TOKEN, db, ip_address=_IP, user_agent=_UA) == (True, True)

    def test_a_token_presented_nine_seconds_after_its_rotation_is_inside_the_window(self, db):
        _rotate(db)
        _age(db, 9)

        assert rotated_service.check_token_reuse(_TOKEN, db, ip_address=_IP, user_agent=_UA) == (True, True)

    def test_a_token_presented_eleven_seconds_after_its_rotation_is_theft(self, db):
        _rotate(db)
        _age(db, 11)

        assert rotated_service.check_token_reuse(_TOKEN, db, ip_address=_IP, user_agent=_UA) == (True, False)

    @pytest.mark.parametrize(("ip", "ua"), [("203.0.113.8", _UA), (_IP, "Endurain/1.1")])
    def test_another_ipv4_address_or_user_agent_is_theft_even_inside_the_window(self, db, ip, ua):
        _rotate(db)

        assert rotated_service.check_token_reuse(_TOKEN, db, ip_address=ip, user_agent=ua) == (True, False)
        assert rotated_service.get_grace_replay_token(_TOKEN, db, ip_address=ip, user_agent=ua) is None

    def test_another_ipv6_64_is_theft_and_the_same_64_with_another_host_part_is_the_same_client(self, db):
        _rotate(db, ip="2001:db8:0:1::1")

        other = rotated_service.check_token_reuse(_TOKEN, db, ip_address="2001:db8:0:2::1", user_agent=_UA)
        same = rotated_service.check_token_reuse(_TOKEN, db, ip_address="2001:db8:0:1::ffff", user_agent=_UA)

        assert (other, same) == ((True, False), (True, True))

    def test_the_logs_name_a_fingerprint_not_the_family_id_and_say_when_another_client_presented_it(self, db, caplog):
        family = _rotate(db)

        with caplog.at_level("WARNING"):
            rotated_service.check_token_reuse(_TOKEN, db, ip_address="198.51.100.1", user_agent=_UA)

        assert "another client" in caplog.text
        assert str(family) not in caplog.text
        assert str(family) not in str([record.__dict__ for record in caplog.records])

    def test_the_logs_of_a_reuse_after_the_window_name_a_fingerprint_not_the_family_id(self, db, caplog):
        family = _rotate(db)
        _age(db, 30)

        with caplog.at_level("WARNING"):
            rotated_service.check_token_reuse(_TOKEN, db, ip_address=_IP, user_agent=_UA)

        assert "after grace period" in caplog.text
        assert str(family) not in str([record.__dict__ for record in caplog.records])


class TestGraceReplay:
    def test_the_rotating_client_gets_the_replacement_and_its_expiry(self, db):
        _rotate(db)

        replay = rotated_service.get_grace_replay_token(_TOKEN, db, ip_address=_IP, user_agent=_UA)

        assert replay is not None
        assert replay[0] == "replacement-token"
        assert replay[1] > datetime.now(UTC)

    def test_an_unknown_token_has_nothing_to_replay(self, db):
        assert rotated_service.get_grace_replay_token("fresh-token", db, ip_address=_IP, user_agent=_UA) is None

    def test_past_the_window_there_is_nothing_to_replay(self, db):
        _rotate(db)
        _age(db, 11)

        assert rotated_service.get_grace_replay_token(_TOKEN, db, ip_address=_IP, user_agent=_UA) is None

    def test_a_record_without_a_stored_replacement_replays_nothing(self, db):
        _rotate(db)
        db.execute(sa.update(rotated_models.RotatedRefreshToken).values(replacement_refresh_token=None))

        assert rotated_service.get_grace_replay_token(_TOKEN, db, ip_address=_IP, user_agent=_UA) is None

    def test_a_replacement_that_cannot_be_decrypted_is_a_server_error_not_a_replay(self, db):
        _rotate(db)
        db.execute(sa.update(rotated_models.RotatedRefreshToken).values(replacement_refresh_token="not-fernet"))

        with pytest.raises(core_exceptions.CryptographyError):
            rotated_service.get_grace_replay_token(_TOKEN, db, ip_address=_IP, user_agent=_UA)

    def test_a_replacement_cleared_after_the_window_does_not_weaken_reuse_detection(self, db):
        _rotate(db)
        _age(db, 11)

        assert rotated_service.clear_expired_replacements(datetime.now(UTC), db) == 1

        assert rotated_service.check_token_reuse(_TOKEN, db, ip_address=_IP, user_agent=_UA) == (True, False)
        assert rotated_service.get_grace_replay_token(_TOKEN, db, ip_address=_IP, user_agent=_UA) is None


class TestKeyRotation:
    """A token rotated under the old ``SECRET_KEY`` is still recognised once the key list is ``new,old``."""

    _OLD = "o" * 40
    _NEW = "n" * 40

    def test_reuse_of_a_token_rotated_under_the_old_key_is_detected_while_the_old_key_is_listed(self, db, secret_key):
        secret_key(self._OLD)
        _rotate(db)

        secret_key(f"{self._NEW},{self._OLD}")
        found = rotated_service.check_token_reuse(_TOKEN, db, ip_address=_IP, user_agent=_UA)
        secret_key(self._NEW)
        unseen = rotated_service.check_token_reuse(_TOKEN, db, ip_address=_IP, user_agent=_UA)

        assert found == (True, True)
        assert unseen == (False, False)

    def test_new_records_are_hashed_with_the_first_key(self, secret_key):
        secret_key(f"{self._NEW},{self._OLD}")

        first = rotated_service.hmac_hash_token("t")
        candidates = rotated_service.hmac_hash_token_candidates("t")

        assert candidates[0] == first
        assert len(set(candidates)) == 2


class TestCleanup:
    def test_expired_records_go_and_the_rest_stay(self, db):
        _rotate(db, "expired", exp=datetime.now(UTC) - timedelta(minutes=1))
        kept = _rotate(db, "live", exp=datetime.now(UTC) + timedelta(days=1))

        assert rotated_service.delete_expired_tokens(datetime.now(UTC), db) == 1

        assert [row.token_family_id for row in _rows(db)] == [kept]

    def test_a_purge_removes_a_full_batch_and_the_rest_in_the_next(self, db):
        count = core_database.PURGE_BATCH_SIZE + 1
        now = datetime.now(UTC)
        family = make_session(db, make_user(db)).token_family_id
        db.execute(
            sa.insert(rotated_models.RotatedRefreshToken),
            [
                {
                    "id": uuid.uuid4(),
                    "token_family_id": family,
                    "hashed_token": f"{index:064x}",
                    "client_fingerprint": "f" * 64,
                    "rotation_count": 1,
                    "rotated_at": now - timedelta(days=1),
                    "expires_at": now - timedelta(days=1),
                    "refresh_token_exp": now - timedelta(minutes=1),
                }
                for index in range(count)
            ],
        )

        assert rotated_service.delete_expired_tokens(now, db) == count
        assert _rows(db) == []

    def test_a_replacement_is_cleared_once_the_window_has_passed_and_the_record_stays(self, db):
        _rotate(db, "in-window")
        stale = _rotate(db, "stale")
        db.execute(
            sa.update(rotated_models.RotatedRefreshToken)
            .where(rotated_models.RotatedRefreshToken.token_family_id == stale)
            .values(expires_at=datetime.now(UTC) - timedelta(seconds=1))
        )

        assert rotated_service.clear_expired_replacements(datetime.now(UTC), db) == 1

        by_family = {row.token_family_id: row for row in _rows(db)}
        assert by_family[stale].replacement_refresh_token is None
        assert by_family[stale].replacement_refresh_token_exp is None
        assert len(by_family) == 2
        assert sum(row.replacement_refresh_token is not None for row in by_family.values()) == 1

    def test_clearing_replacements_is_bounded_by_the_limit(self, db):
        for token in ("a", "b", "c"):
            _rotate(db, token)
        _age(db, 30)

        assert rotated_crud.clear_expired_replacements(datetime.now(UTC), 2, db) == 2

    def test_a_family_deletes_with_its_records_only(self, db):
        family = _rotate(db, "first")
        _rotate(db, "other")

        assert rotated_integration.delete_by_family(family, db) == 1

        assert len(_rows(db)) == 1

    def test_the_cleanup_job_clears_ended_windows_and_deletes_expired_records_in_its_own_session(
        self, committed_sessions
    ):
        with committed_sessions() as db:
            _rotate(db, "expired", exp=datetime.now(UTC) - timedelta(minutes=1))
            _rotate(db, "stale")
            _rotate(db, "live")
            db.execute(
                sa.update(rotated_models.RotatedRefreshToken)
                .where(rotated_models.RotatedRefreshToken.hashed_token == rotated_service.hmac_hash_token("stale"))
                .values(expires_at=datetime.now(UTC) - timedelta(seconds=1))
            )
            db.commit()

        rotated_scheduled_jobs.delete_expired_rotated_tokens()

        with committed_sessions() as db:
            rows = {row.hashed_token: row for row in _rows(db)}
        assert set(rows) == {rotated_service.hmac_hash_token("stale"), rotated_service.hmac_hash_token("live")}
        assert rows[rotated_service.hmac_hash_token("stale")].replacement_refresh_token is None
        assert rows[rotated_service.hmac_hash_token("live")].replacement_refresh_token is not None


class TestReencryption:
    def test_reencryption_skips_a_cleared_replacement_and_keeps_the_rest_readable(self, db):
        _rotate(db, "kept")
        cleared = _rotate(db, "cleared")
        db.execute(
            sa.update(rotated_models.RotatedRefreshToken)
            .where(rotated_models.RotatedRefreshToken.token_family_id == cleared)
            .values(replacement_refresh_token=None, replacement_refresh_token_exp=None)
        )

        rotated_service.reencrypt_stored_secrets(db)

        assert rotated_service.get_grace_replay_token("kept", db, ip_address=_IP, user_agent=_UA) is not None
        assert rotated_service.get_grace_replay_token("cleared", db, ip_address=_IP, user_agent=_UA) is None

    def test_the_reencryption_job_runs_in_its_own_session(self, committed_sessions):
        with committed_sessions() as db:
            _rotate(db, "kept")
            db.commit()

        rotated_scheduled_jobs.reencrypt_stored_secrets()

        with committed_sessions() as db:
            assert rotated_service.get_grace_replay_token("kept", db, ip_address=_IP, user_agent=_UA) is not None
