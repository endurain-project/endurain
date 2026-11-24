"""Session queries and writes, against PostgreSQL: windows, lookups, locks, one-shot claims, deletes and constraints."""

import threading
import uuid
from datetime import UTC, datetime, timedelta

import pytest
import sqlalchemy as sa
from sqlalchemy.exc import IntegrityError

import core.database as core_database
import core.exceptions as core_exceptions
import modules.auth.constants as auth_constants
import modules.auth.sessions.crud as sessions_crud
import modules.auth.sessions.models as sessions_models
import modules.auth.sessions.schema as sessions_schema
from tests._factories.auth import make_session
from tests._factories.users import make_user


def _row_values(session) -> dict:
    return {c.name: getattr(session, c.name) for c in sessions_models.UsersSessions.__table__.columns}


class TestWindow:
    def test_a_page_is_newest_first_with_the_id_as_tiebreak_and_hides_unexchanged_sessions(self, db):
        user = make_user(db)
        now = datetime.now(UTC)
        oldest = make_session(db, user, created_at=now - timedelta(hours=2))
        newest = make_session(db, user, created_at=now - timedelta(hours=1))
        make_session(db, user, exchanged=False)
        make_session(db, make_user(db))

        everything = sessions_crud.get_user_sessions_page(user.id, db, limit=10, offset=0)
        window = sessions_crud.get_user_sessions_page(user.id, db, limit=1, offset=1)

        assert [s.id for s in everything] == [newest.id, oldest.id]
        assert [s.id for s in window] == [oldest.id]
        assert sessions_crud.count_user_sessions(user.id, db) == 2

    def test_a_user_with_no_sessions_has_an_empty_page_and_a_zero_count(self, db):
        user = make_user(db)

        assert sessions_crud.get_user_sessions_page(user.id, db, limit=10, offset=0) == []
        assert sessions_crud.count_user_sessions(user.id, db) == 0

    def test_existing_session_ids_names_only_the_sessions_that_still_exist(self, db):
        user = make_user(db)
        kept = make_session(db, user)

        assert sessions_crud.get_existing_session_ids([kept.id, uuid.uuid4()], db) == {kept.id}
        assert sessions_crud.get_existing_session_ids([], db) == set()


class TestLookup:
    def test_a_session_reads_back_with_its_client_type_auth_time_and_methods(self, db):
        user = make_user(db)
        stored = make_session(db, user, client_type=auth_constants.ClientType.MOBILE)

        read = sessions_crud.get_session_by_id(stored.id, db)

        assert read is not None
        assert read.client_type is auth_constants.ClientType.MOBILE
        assert read.amr == ["pwd"]
        assert read.auth_time == stored.created_at

    def test_a_missing_session_reads_as_none(self, db):
        assert sessions_crud.get_session_by_id(uuid.uuid4(), db) is None

    def test_a_session_is_read_by_its_owner_only(self, db):
        owner, other = make_user(db), make_user(db)
        session = make_session(db, owner)

        assert sessions_crud.get_session_by_id_and_user_id(session.id, owner.id, db) is not None
        assert sessions_crud.get_session_by_id_and_user_id(session.id, other.id, db) is None

    def test_an_expired_session_is_not_a_live_one(self, db):
        user = make_user(db)
        live = make_session(db, user)
        expired = make_session(db, user, expires_at=datetime.now(UTC) - timedelta(minutes=1))

        assert sessions_crud.get_session_by_id_not_expired(live.id, db) is not None
        assert sessions_crud.get_session_by_id_not_expired(expired.id, db) is None
        assert sessions_crud.lock_live_session(live.id, db) is not None
        assert sessions_crud.lock_live_session(expired.id, db, exclusive=True) is None


class TestWrites:
    def test_editing_a_session_that_is_gone_is_not_found(self, db):
        user = make_user(db)
        session = make_session(db, user)
        db.execute(sa.delete(sessions_models.UsersSessions))

        with pytest.raises(core_exceptions.NotFoundError):
            sessions_crud.edit_session(sessions_schema.UserSessionsInternal(**_row_values(session)), db)

    def test_setting_the_refresh_token_hash_of_a_missing_session_is_not_found(self, db):
        with pytest.raises(core_exceptions.NotFoundError):
            sessions_crud.set_session_refresh_token_hash(uuid.uuid4(), "digest", db)

    def test_setting_the_refresh_token_hash_stores_it(self, db):
        session = make_session(db, make_user(db))

        sessions_crud.set_session_refresh_token_hash(session.id, "digest", db)

        assert sessions_crud.get_session_by_id(session.id, db).refresh_token == "digest"

    def test_the_claim_is_conditional_and_sets_the_real_expiry(self, db):
        pending = make_session(db, make_user(db), exchanged=False, expires_at=datetime.now(UTC) + timedelta(minutes=5))
        real_expiry = datetime.now(UTC) + timedelta(days=30)

        assert sessions_crud.claim_session_for_token_exchange(
            pending.id, "hashed", real_expiry, ["fed", "otp", "mfa"], db
        )
        assert not sessions_crud.claim_session_for_token_exchange(pending.id, "again", real_expiry, ["fed"], db)

        claimed = sessions_crud.get_session_by_id(pending.id, db)
        assert (claimed.tokens_exchanged, claimed.refresh_token, claimed.amr) == (True, "hashed", ["fed", "otp", "mfa"])
        assert claimed.expires_at == real_expiry

    def test_clearing_the_oauth_state_reference_leaves_the_session(self, db):
        user = make_user(db)
        import modules.auth.oauth_state.constants as oauth_state_constants
        import modules.auth.oauth_state.integration_service as oauth_state_integration

        oauth_state_integration.create_oauth_state(
            "state-1", "n" * 32, "web", "127.0.0.1", db, purpose=oauth_state_constants.OAuthStatePurpose.LOGIN
        )
        session = make_session(db, user, exchanged=False, oauth_state_id="state-1")

        sessions_crud.clear_oauth_state_reference(session.id, db)

        assert sessions_crud.get_session_by_id(session.id, db).oauth_state_id is None


class TestDeletes:
    def test_a_session_is_deleted_by_its_owner_and_a_missing_or_unowned_one_is_not_found(self, db):
        owner, other = make_user(db), make_user(db)
        session = make_session(db, owner)

        with pytest.raises(core_exceptions.NotFoundError):
            sessions_crud.delete_session(session.id, other.id, db)
        with pytest.raises(core_exceptions.NotFoundError):
            sessions_crud.delete_session(uuid.uuid4(), owner.id, db)
        assert sessions_crud.get_session_by_id(session.id, db) is not None
        assert sessions_crud.delete_session(session.id, owner.id, db).id == session.id
        assert sessions_crud.get_session_by_id(session.id, db) is None

    def test_deleting_a_session_that_may_be_gone_returns_none_when_it_is(self, db):
        user = make_user(db)

        assert sessions_crud.delete_session_if_present(uuid.uuid4(), user.id, db) is None

    def test_the_bulk_delete_counts_the_users_sessions_and_keeps_the_excluded_and_others(self, db):
        user, other = make_user(db), make_user(db)
        kept = make_session(db, user)
        make_session(db, user)
        make_session(db, user)
        theirs = make_session(db, other)

        assert sessions_crud.delete_sessions_by_user(user.id, db, kept.id) == 2

        assert sessions_crud.count_user_sessions(user.id, db) == 1
        assert sessions_crud.get_session_by_id(theirs.id, db) is not None

    def test_the_family_lookup_and_delete_name_and_end_the_family_sessions(self, db):
        user = make_user(db)
        session = make_session(db, user)
        other = make_session(db, user)

        assert sessions_crud.list_session_owners_by_family(session.token_family_id, db) == [(user.id, session.id)]
        assert sessions_crud.delete_sessions_by_family(session.token_family_id, db) == 1
        assert sessions_crud.get_session_by_id(other.id, db) is not None

    def test_the_oauth_state_ids_of_a_users_sessions_leave_out_the_excluded_one(self, db):
        import modules.auth.oauth_state.constants as oauth_state_constants
        import modules.auth.oauth_state.integration_service as oauth_state_integration

        user = make_user(db)
        for state_id in ("st-a", "st-b"):
            oauth_state_integration.create_oauth_state(
                state_id, "n" * 32, "web", "127.0.0.1", db, purpose=oauth_state_constants.OAuthStatePurpose.LOGIN
            )
        first = make_session(db, user, exchanged=False, oauth_state_id="st-a")
        make_session(db, user, exchanged=False, oauth_state_id="st-b")
        make_session(db, user)

        assert sorted(sessions_crud.list_oauth_state_ids_by_user(user.id, db)) == ["st-a", "st-b"]
        assert sessions_crud.list_oauth_state_ids_by_user(user.id, db, first.id) == ["st-b"]

    def test_the_device_delete_removes_only_the_users_sessions_of_that_device(self, db):
        user, other = make_user(db), make_user(db)
        gone = make_session(db, user, device_hash="a" * 64)
        elsewhere = make_session(db, user, device_hash="b" * 64)
        theirs = make_session(db, other, device_hash="a" * 64)

        removed = sessions_crud.delete_sessions_by_device(user.id, "a" * 64, db)

        assert [s.id for s in removed] == [gone.id]
        assert sessions_crud.get_session_by_id(elsewhere.id, db) is not None
        assert sessions_crud.get_session_by_id(theirs.id, db) is not None


class TestPurge:
    def test_the_expired_purge_removes_an_expired_unexchanged_session_and_keeps_a_live_one(self, db):
        user = make_user(db)
        expired = make_session(db, user, exchanged=False, expires_at=datetime.now(UTC) - timedelta(minutes=1))
        live = make_session(db, user, exchanged=False, expires_at=datetime.now(UTC) + timedelta(minutes=5))

        removed = sessions_crud.delete_expired_sessions(datetime.now(UTC), 100, db)

        assert removed == [(user.id, expired.id)]
        assert sessions_crud.get_session_by_id(live.id, db) is not None

    def test_a_purge_removes_at_most_its_limit(self, db):
        user = make_user(db)
        for _ in range(3):
            make_session(db, user, expires_at=datetime.now(UTC) - timedelta(minutes=1))

        assert len(sessions_crud.delete_expired_sessions(datetime.now(UTC), 2, db)) == 2

    def test_the_idle_purge_removes_sessions_last_active_before_the_cutoff(self, db):
        user = make_user(db)
        idle = make_session(db, user, last_activity_at=datetime.now(UTC) - timedelta(hours=3))
        active = make_session(db, user)

        removed = sessions_crud.delete_idle_sessions(datetime.now(UTC) - timedelta(hours=1), 100, db)

        assert removed == [(user.id, idle.id)]
        assert sessions_crud.get_session_by_id(active.id, db) is not None


class TestConstraints:
    def test_a_session_of_an_unknown_client_type_is_refused_by_the_database(self, db):
        session = make_session(db, make_user(db))
        values = _row_values(session) | {"id": uuid.uuid4(), "token_family_id": uuid.uuid4(), "client_type": "desktop"}

        with pytest.raises(IntegrityError), db.begin_nested():
            db.execute(sa.insert(sessions_models.UsersSessions).values(**values))

    def test_a_session_of_a_user_that_does_not_exist_is_refused_by_the_database(self, db):
        session = make_session(db, make_user(db))
        values = _row_values(session) | {"id": uuid.uuid4(), "token_family_id": uuid.uuid4(), "user_id": uuid.uuid4()}

        with pytest.raises(IntegrityError), db.begin_nested():
            db.execute(sa.insert(sessions_models.UsersSessions).values(**values))

    def test_deleting_a_user_deletes_their_sessions(self, db):
        import modules.users.users.models as users_models

        user = make_user(db)
        session = make_session(db, user)

        db.execute(sa.delete(users_models.Users).where(users_models.Users.id == user.id))

        assert sessions_crud.get_session_by_id(session.id, db) is None


class TestRowLocks:
    """A live session read for a rotation holds its row, so a revocation waits for the rotation to commit."""

    @staticmethod
    def _waiting_for_a_lock() -> int:
        """Count the sessions waiting on a lock; a poll on its own autocommit connection sees a new wait."""
        with core_database.engine.connect().execution_options(isolation_level="AUTOCOMMIT") as connection:
            return connection.execute(
                sa.text(
                    "SELECT count(*) FROM pg_stat_activity "
                    "WHERE wait_event_type = 'Lock' AND datname = current_database()"
                )
            ).scalar_one()

    @classmethod
    def _wait_until_blocked(cls) -> None:
        for _ in range(200):
            if cls._waiting_for_a_lock():
                return
            threading.Event().wait(0.05)
        raise AssertionError("the second session never waited for the lock")

    def _arrange(self, committed_sessions) -> tuple[uuid.UUID, uuid.UUID]:
        with committed_sessions() as db:
            user = make_user(db)
            session = make_session(db, user)
            db.commit()
        return user.id, session.id

    def test_an_exclusive_lock_queues_a_second_exclusive_reader_until_the_first_commits(self, committed_sessions):
        _, session_id = self._arrange(committed_sessions)
        order: list[str] = []

        def second() -> None:
            with committed_sessions() as db:
                assert sessions_crud.lock_live_session(session_id, db, exclusive=True) is not None
                order.append("second")
                db.commit()

        with committed_sessions() as first:
            assert sessions_crud.lock_live_session(session_id, first, exclusive=True) is not None
            thread = threading.Thread(target=second)
            thread.start()
            self._wait_until_blocked()
            order.append("first")
            first.commit()
        thread.join(timeout=20)

        assert order == ["first", "second"]

    def test_a_shared_lock_does_not_queue_another_shared_reader_but_holds_back_a_delete(self, committed_sessions):
        user_id, session_id = self._arrange(committed_sessions)
        order: list[str] = []

        def revoke() -> None:
            with committed_sessions() as db:
                sessions_crud.delete_session(session_id, user_id, db)
                order.append("revoked")
                db.commit()

        with committed_sessions() as reader, committed_sessions() as another:
            assert sessions_crud.lock_live_session(session_id, reader) is not None
            assert sessions_crud.lock_live_session(session_id, another) is not None
            thread = threading.Thread(target=revoke)
            thread.start()
            self._wait_until_blocked()
            order.append("reader done")
            another.commit()
            reader.commit()
        thread.join(timeout=20)

        assert order == ["reader done", "revoked"]
        with committed_sessions() as db:
            assert sessions_crud.get_session_by_id(session_id, db) is None
