"""Locking unverified sign-ups to purge them uses ``FOR UPDATE SKIP LOCKED`` against real PostgreSQL.

The hourly purge runs on every replica that wins its lock and may overlap a verification or a second purge: a row
somebody else holds must be skipped without waiting, and no sign-up may be handed to two purges.
"""

import threading
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import select, text
from tests._factories.users import make_user

import modules.auth.credentials.models as credentials_models
import modules.users.users.crud as users_crud

_OLD = datetime.now(UTC) - timedelta(days=3)
_CUTOFF = datetime.now(UTC) - timedelta(days=1)


def _sign_up(factory, **fields: object) -> uuid.UUID:
    """Store an unverified self sign-up created three days ago, with no credential unless asked."""
    values = {"active": False, "email_verified": False, "deactivated_at": None, "created_at": _OLD, **fields}
    with factory() as db:
        user_id = make_user(db, with_password=False, **values).id
        db.commit()
    return user_id


def _held() -> list:
    return [select(credentials_models.LocalCredential.user_id)]


def _lock(db, limit: int = 100) -> list[uuid.UUID]:
    return users_crud.lock_unverified_sign_ups(_CUTOFF, _held(), limit, db)


class TestLockUnverifiedSignUps:
    def test_only_old_unverified_inactive_sign_ups_are_locked_in_id_order(self, committed_sessions):
        stale = sorted(_sign_up(committed_sessions) for _ in range(3))
        _sign_up(committed_sessions, created_at=datetime.now(UTC))
        _sign_up(committed_sessions, email_verified=True)
        _sign_up(committed_sessions, active=True)
        _sign_up(committed_sessions, deactivated_at=datetime.now(UTC))
        _sign_up(committed_sessions, deletion_requested_at=datetime.now(UTC))

        with committed_sessions() as db:
            assert _lock(db) == stale

    def test_a_sign_up_with_a_credential_is_kept(self, committed_sessions):
        with_credential = _sign_up(committed_sessions)
        without = _sign_up(committed_sessions)
        with committed_sessions() as db:
            db.add(credentials_models.LocalCredential(user_id=with_credential, password_hash="hash"))
            db.commit()

        with committed_sessions() as db:
            assert _lock(db) == [without]

    def test_the_limit_bounds_the_rows_locked_and_the_rest_wait_for_the_next_call(self, committed_sessions):
        ids = sorted(_sign_up(committed_sessions) for _ in range(5))

        with committed_sessions() as db:
            assert _lock(db, limit=2) == ids[:2]

    def test_a_row_another_transaction_holds_is_skipped_without_waiting(self, committed_sessions):
        held, free = sorted((_sign_up(committed_sessions), _sign_up(committed_sessions)))
        with committed_sessions() as verifying, committed_sessions() as purging:
            verifying.execute(text("SELECT id FROM users WHERE id = :i FOR UPDATE"), {"i": held})
            purging.execute(text("SET lock_timeout = '2s'"))

            assert _lock(purging) == [free]

    def test_a_row_that_stopped_qualifying_while_locked_is_left_out(self, committed_sessions):
        gone, kept = sorted((_sign_up(committed_sessions), _sign_up(committed_sessions)))
        with committed_sessions() as db:
            assert _lock(db) == sorted((gone, kept))
        with committed_sessions() as verifying:
            verifying.execute(text("UPDATE users SET email_verified = true WHERE id = :i"), {"i": gone})
            verifying.commit()

        with committed_sessions() as db:
            assert _lock(db) == [kept]

    def test_purges_running_together_lock_each_sign_up_once(self, committed_sessions):
        ids = {_sign_up(committed_sessions) for _ in range(12)}
        started, all_locked = threading.Barrier(4), threading.Barrier(4)
        locked: list[list[uuid.UUID]] = []
        errors: list[Exception] = []

        def purge() -> None:
            try:
                with committed_sessions() as db:
                    started.wait()
                    locked.append(_lock(db, limit=3))
                    # Each purge holds its rows until every purge has locked, as one that is still deleting them does.
                    all_locked.wait()
                    db.commit()
            except Exception as err:
                errors.append(err)

        threads = [threading.Thread(target=purge) for _ in range(4)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=30)

        everything = [user_id for batch in locked for user_id in batch]
        assert errors == []
        assert len(everything) == len(set(everything)) == 12
        assert set(everything) == ids
