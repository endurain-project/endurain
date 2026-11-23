"""Provider token writes against a session that holds the integrations row, on PostgreSQL.

``unlink_strava_tokens_if_refresh_token`` and ``stage_reencrypt_batch_garmin`` lock the row they read, so a second
session waits for the first instead of acting on a stale copy. Each test holds the row in one session, starts the
other on a thread, waits until it blocks on the lock (``pg_stat_activity``), commits the first, and reads the outcome
back in a new session. ``stage_reencrypt_batch_strava`` takes no lock; it rewrites a value only while it is still the
ciphertext that was read, so its test commits a write between the read and the rewrite.
"""

import uuid
from datetime import UTC, datetime
from typing import Any

import pytest
from cryptography.fernet import Fernet
from sqlalchemy import select, update

import core.cryptography as core_cryptography
import modules.users.users_integrations.crud as integrations_crud
import modules.users.users_integrations.models as integrations_models
from tests._factories.garmin import link_garmin
from tests._factories.strava import CLIENT_ID, link_strava
from tests._factories.users import make_user
from tests._helpers.concurrency import Worker, wait_until_a_session_waits_for_a_lock

_NEW_KEY = Fernet.generate_key().decode()
_OLD_KEY = Fernet.generate_key().decode()
_STRANGER_KEY = Fernet.generate_key().decode()

_Model = integrations_models.UsersIntegrations


def _under(key: str, plaintext: str) -> str:
    """Encrypt ``plaintext`` under ``key`` alone."""
    return Fernet(key.encode()).encrypt(plaintext.encode()).decode()


def _opens_under(key: str, token: str) -> bool:
    """Report whether ``key`` alone decrypts ``token``."""
    try:
        Fernet(key.encode()).decrypt(token.encode())
    except Exception:
        return False
    return True


def _row(factory, user_id: uuid.UUID) -> Any:
    """The user's integrations row as stored, read in a session of its own."""
    with factory() as db:
        row = db.execute(select(_Model).where(_Model.user_id == user_id)).scalar_one()
        db.expunge(row)
        return row


@pytest.fixture
def strava_user(committed_sessions) -> uuid.UUID:
    """A committed user with Strava linked under the refresh token ``refresh-old``."""
    with committed_sessions() as db:
        user_id = make_user(db).id
        link_strava(db, user_id, access_token="access-old", refresh_token="refresh-old")
        db.commit()
    return user_id


class TestStravaUnlinkIfRefreshToken:
    def test_a_matching_token_is_cleared_and_the_revocation_is_stored(self, committed_sessions, strava_user):
        old = _row(committed_sessions, strava_user).strava_refresh_token
        revoked_at = datetime(2026, 1, 2, 3, 4, tzinfo=UTC)

        with committed_sessions() as db:
            cleared = integrations_crud.unlink_strava_tokens_if_refresh_token(
                strava_user, old, db, revoked_at=revoked_at
            )
            db.commit()

        row = _row(committed_sessions, strava_user)
        assert cleared is True
        assert (row.strava_token, row.strava_refresh_token, row.strava_token_expires_at) == (None, None, None)
        assert row.strava_revoked_at == revoked_at
        assert core_cryptography.decrypt_token_fernet(row.strava_client_id) == CLIENT_ID

    def test_a_matching_token_is_cleared_without_marking_it_revoked_when_no_time_is_given(
        self, committed_sessions, strava_user
    ):
        old = _row(committed_sessions, strava_user).strava_refresh_token

        with committed_sessions() as db:
            cleared = integrations_crud.unlink_strava_tokens_if_refresh_token(strava_user, old, db)
            db.commit()

        row = _row(committed_sessions, strava_user)
        assert cleared is True
        assert row.strava_refresh_token is None
        assert row.strava_revoked_at is None

    def test_an_unlink_waits_for_a_refresh_and_then_leaves_the_new_tokens(self, committed_sessions, strava_user):
        old = _row(committed_sessions, strava_user).strava_refresh_token
        refreshed = {"access_token": "access-new", "refresh_token": "refresh-new", "expires_at": 2_000_000_000}

        with committed_sessions() as refresher:
            assert integrations_crud.replace_strava_tokens_if_refresh_token(strava_user, old, refreshed, refresher)

            def unlink() -> bool:
                with committed_sessions() as db:
                    cleared = integrations_crud.unlink_strava_tokens_if_refresh_token(
                        strava_user, old, db, revoked_at=datetime.now(UTC)
                    )
                    db.commit()
                return cleared

            worker = Worker(unlink)
            wait_until_a_session_waits_for_a_lock(committed_sessions)
            refresher.commit()
            worker.join()

        row = _row(committed_sessions, strava_user)
        assert worker.error is None
        assert worker.result is False
        assert core_cryptography.decrypt_token_fernet(row.strava_refresh_token) == "refresh-new"
        assert core_cryptography.decrypt_token_fernet(row.strava_token) == "access-new"
        assert row.strava_revoked_at is None


class TestGarminReencryptionBatch:
    @pytest.fixture
    def rotating_keys(self, monkeypatch) -> None:
        """Configure the new key first and the old key second."""
        monkeypatch.setenv("FERNET_KEY", f"{_NEW_KEY},{_OLD_KEY}")

    @staticmethod
    def _garmin_token(**secrets: str) -> dict[str, Any]:
        return {"di_client_id": "client-1", "is_cn": False, **secrets}

    def _store_token(self, committed_sessions, token: dict[str, Any]) -> uuid.UUID:
        with committed_sessions() as db:
            user_id = make_user(db).id
            integrations_crud.link_garminconnect_account(user_id, token, db)
            db.commit()
        return user_id

    def test_the_secrets_move_to_the_first_key_and_other_fields_stay(self, committed_sessions, rotating_keys):
        token = self._garmin_token(di_token=_under(_OLD_KEY, "access"), di_refresh_token=_under(_OLD_KEY, "refresh"))
        user_id = self._store_token(committed_sessions, token)

        with committed_sessions() as db:
            batch = integrations_crud.stage_reencrypt_batch_garmin(None, 10, db)
            db.commit()

        stored = _row(committed_sessions, user_id).garminconnect_token
        assert batch.counts.rotated == 2
        assert batch.counts.undecryptable == 0
        assert _opens_under(_NEW_KEY, stored["di_token"]) and _opens_under(_NEW_KEY, stored["di_refresh_token"])
        assert core_cryptography.decrypt_token_fernet(stored["di_token"]) == "access"
        assert core_cryptography.decrypt_token_fernet(stored["di_refresh_token"]) == "refresh"
        assert (stored["di_client_id"], stored["is_cn"]) == ("client-1", False)

    def test_a_secret_no_key_opens_is_left_as_it_is_and_counted(self, committed_sessions, rotating_keys):
        stranger = _under(_STRANGER_KEY, "foreign")
        token = self._garmin_token(di_token=_under(_OLD_KEY, "access"), di_refresh_token=stranger)
        user_id = self._store_token(committed_sessions, token)

        with committed_sessions() as db:
            batch = integrations_crud.stage_reencrypt_batch_garmin(None, 10, db)
            db.commit()

        stored = _row(committed_sessions, user_id).garminconnect_token
        assert (batch.counts.rotated, batch.counts.undecryptable) == (1, 1)
        assert stored["di_refresh_token"] == stranger
        assert _opens_under(_NEW_KEY, stored["di_token"])

    def test_a_secret_already_under_the_first_key_is_not_rewritten(self, committed_sessions, rotating_keys):
        current = _under(_NEW_KEY, "access")
        user_id = self._store_token(committed_sessions, self._garmin_token(di_token=current, di_refresh_token=None))

        with committed_sessions() as db:
            batch = integrations_crud.stage_reencrypt_batch_garmin(None, 10, db)
            db.commit()

        assert (batch.counts.rotated, batch.counts.undecryptable) == (0, 0)
        assert _row(committed_sessions, user_id).garminconnect_token["di_token"] == current

    def test_the_cursor_walks_the_rows_in_id_order_a_limit_at_a_time(self, committed_sessions, rotating_keys):
        for n in range(3):
            self._store_token(committed_sessions, self._garmin_token(di_token=_under(_OLD_KEY, f"access-{n}")))
        with committed_sessions() as db:
            ids = list(db.scalars(select(_Model.id).order_by(_Model.id)))

        with committed_sessions() as db:
            first = integrations_crud.stage_reencrypt_batch_garmin(None, 2, db)
            second = integrations_crud.stage_reencrypt_batch_garmin(first.last_id, 2, db)
            third = integrations_crud.stage_reencrypt_batch_garmin(second.last_id, 2, db)
            db.commit()

        assert (first.last_id, second.last_id, third.last_id) == (ids[1], ids[2], None)
        assert (first.counts.rotated, second.counts.rotated, third.counts.rotated) == (2, 1, 0)

    def test_a_token_write_started_during_a_batch_waits_and_survives_it(self, committed_sessions, rotating_keys):
        old = self._garmin_token(di_token=_under(_OLD_KEY, "access-old"), di_refresh_token=_under(_OLD_KEY, "r-old"))
        user_id = self._store_token(committed_sessions, old)
        written = self._garmin_token(
            di_token=_under(_NEW_KEY, "access-new"), di_refresh_token=_under(_NEW_KEY, "r-new")
        )

        with committed_sessions() as batch_session:
            integrations_crud.stage_reencrypt_batch_garmin(None, 10, batch_session)

            def write() -> None:
                with committed_sessions() as db:
                    integrations_crud.link_garminconnect_account(user_id, written, db)
                    db.commit()

            worker = Worker(write)
            wait_until_a_session_waits_for_a_lock(committed_sessions)
            batch_session.commit()
            worker.join()

        assert worker.error is None
        assert _row(committed_sessions, user_id).garminconnect_token == written

    def test_a_refresh_started_while_the_batch_reads_waits_and_lands_after_it(
        self, committed_sessions, rotating_keys, monkeypatch
    ):
        old = self._garmin_token(di_token=_under(_OLD_KEY, "access-old"), di_refresh_token=_under(_OLD_KEY, "r-old"))
        user_id = self._store_token(committed_sessions, old)
        refreshed = self._garmin_token(di_token=_under(_NEW_KEY, "access-new"), di_refresh_token=_under(_NEW_KEY, "r"))
        workers: list[Worker] = []
        original = core_cryptography.reencrypt_to_primary_key

        def refresh() -> bool:
            with committed_sessions() as db:
                replaced = integrations_crud.replace_garminconnect_token_if_token(user_id, old, refreshed, db)
                db.commit()
            return replaced

        def reencrypt_while_a_refresh_starts(token: str) -> str | None:
            if not workers:
                workers.append(Worker(refresh))
                # The refresh either blocks on the batch's lock or, with no lock, finishes and commits at once.
                while not workers[0].done:
                    try:
                        wait_until_a_session_waits_for_a_lock(committed_sessions, timeout=0.2)
                    except AssertionError:
                        continue
                    break
            return original(token)

        monkeypatch.setattr(core_cryptography, "reencrypt_to_primary_key", reencrypt_while_a_refresh_starts)

        with committed_sessions() as batch_session:
            integrations_crud.stage_reencrypt_batch_garmin(None, 10, batch_session)
            batch_session.commit()
        workers[0].join()

        assert workers[0].error is None
        assert workers[0].result is True
        assert _row(committed_sessions, user_id).garminconnect_token == refreshed


class TestStravaReencryptionBatch:
    def test_every_strava_column_moves_to_the_first_key_and_garmin_is_left_alone(self, committed_sessions, monkeypatch):
        monkeypatch.setenv("FERNET_KEY", f"{_NEW_KEY},{_OLD_KEY}")
        garmin = {"di_token": _under(_OLD_KEY, "g"), "di_refresh_token": None, "di_client_id": "c"}
        with committed_sessions() as db:
            user_id = make_user(db).id
            link_garmin(db, user_id)
            db.execute(
                update(_Model)
                .where(_Model.user_id == user_id)
                .values(
                    strava_client_id=_under(_OLD_KEY, "client"),
                    strava_client_secret=_under(_OLD_KEY, "secret"),
                    strava_token=_under(_OLD_KEY, "access"),
                    strava_refresh_token=_under(_STRANGER_KEY, "foreign"),
                    garminconnect_token=garmin,
                )
            )
            db.commit()
        stranger = _row(committed_sessions, user_id).strava_refresh_token

        with committed_sessions() as db:
            batch = integrations_crud.stage_reencrypt_batch_strava(None, 10, db)
            db.commit()

        row = _row(committed_sessions, user_id)
        columns = (row.strava_client_id, row.strava_client_secret, row.strava_token)
        assert (batch.counts.rotated, batch.counts.undecryptable) == (3, 1)
        assert all(_opens_under(_NEW_KEY, value) for value in columns)
        assert [core_cryptography.decrypt_token_fernet(value) for value in columns] == ["client", "secret", "access"]
        assert row.strava_refresh_token == stranger
        assert row.garminconnect_token == garmin

    def test_a_token_written_between_the_read_and_the_rewrite_is_not_overwritten(self, committed_sessions, monkeypatch):
        monkeypatch.setenv("FERNET_KEY", f"{_NEW_KEY},{_OLD_KEY}")
        with committed_sessions() as db:
            user_id = make_user(db).id
            db.execute(update(_Model).where(_Model.user_id == user_id).values(strava_token=_under(_OLD_KEY, "stale")))
            db.commit()
        written = _under(_NEW_KEY, "written-meanwhile")
        original = core_cryptography.reencrypt_to_primary_key

        def reencrypt_after_a_committed_write(token: str) -> str | None:
            rewritten = original(token)
            with committed_sessions() as writer:
                writer.execute(update(_Model).where(_Model.user_id == user_id).values(strava_token=written))
                writer.commit()
            return rewritten

        monkeypatch.setattr(core_cryptography, "reencrypt_to_primary_key", reencrypt_after_a_committed_write)

        with committed_sessions() as db:
            batch = integrations_crud.stage_reencrypt_batch_strava(None, 10, db)
            db.commit()

        assert batch.counts.rotated == 0
        assert _row(committed_sessions, user_id).strava_token == written
