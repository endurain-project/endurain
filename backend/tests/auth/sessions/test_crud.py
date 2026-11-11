"""Tests for staged auth-session persistence."""

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import CursorResult
from sqlalchemy.dialects import postgresql
from sqlalchemy.exc import SQLAlchemyError

import core.exceptions as core_exceptions
import modules.auth.sessions.crud as sessions_crud
import modules.auth.sessions.models as sessions_models
import modules.auth.sessions.schema as sessions_schema
from modules.auth.constants import ClientType


def _row(**updates):
    values = {
        "id": "session-id",
        "user_id": 7,
        "refresh_token": "hashed-refresh",
        "ip_address": "127.0.0.1",
        "device_type": "PC",
        "operating_system": "Linux",
        "operating_system_version": "1",
        "browser": "Firefox",
        "browser_version": "1",
        "created_at": datetime.now(UTC),
        "last_activity_at": datetime.now(UTC),
        "expires_at": datetime.now(UTC) + timedelta(days=1),
        "oauth_state_id": None,
        "tokens_exchanged": False,
        "token_family_id": "family-id",
        "rotation_count": 0,
        "last_rotation_at": None,
        "csrf_token_hash": None,
        "client_type": "web",
        "auth_time": datetime.now(UTC),
        "amr": ["pwd"],
    }
    values.update(updates)
    return SimpleNamespace(**values)


def _result(value=None, *, rowcount=1):
    result = MagicMock(spec=CursorResult)
    result.scalar_one_or_none.return_value = value
    result.scalars.return_value = value or []
    result.rowcount = rowcount
    return result


def test_get_user_sessions_page_pushes_the_window_into_the_query(mock_db):
    mock_db.execute.return_value.scalars.return_value = [_row(id="one")]
    result = sessions_crud.get_user_sessions_page(7, mock_db, limit=5, offset=10)
    assert [row.id for row in result] == ["one"]
    compiled = str(mock_db.execute.call_args.args[0].compile(compile_kwargs={"literal_binds": True}))
    assert "ORDER BY users_sessions.created_at DESC, users_sessions.id" in compiled
    assert "LIMIT 5" in compiled and "OFFSET 10" in compiled


def test_count_user_sessions_counts_the_users_rows(mock_db):
    mock_db.execute.return_value.scalar_one.return_value = 4
    assert sessions_crud.count_user_sessions(7, mock_db) == 4
    assert "count" in str(mock_db.execute.call_args.args[0]).lower()


@pytest.mark.parametrize("lookup", [sessions_crud.get_session_by_id, sessions_crud.get_session_by_id_not_expired])
def test_session_lookup_returns_dto_and_none(lookup, mock_db):
    mock_db.execute.return_value = _result(_row())
    result = lookup("session-id", mock_db)
    assert result is not None
    assert result.id == "session-id"
    mock_db.execute.return_value = _result()
    assert lookup("missing", mock_db) is None


def test_lock_live_session_returns_dto_and_none(mock_db):
    mock_db.execute.return_value = _result(_row())
    result = sessions_crud.lock_live_session("session-id", mock_db)
    assert result is not None
    assert result.id == "session-id"
    mock_db.execute.return_value = _result()
    assert sessions_crud.lock_live_session("missing", mock_db) is None


def test_lock_live_session_takes_a_shared_row_lock_on_the_unexpired_session(mock_db):
    mock_db.execute.return_value = _result(_row())

    sessions_crud.lock_live_session("session-id", mock_db)

    statement = str(mock_db.execute.call_args.args[0].compile(dialect=postgresql.dialect()))
    assert "FOR SHARE" in statement
    assert "expires_at >" in statement


def test_lock_live_session_takes_an_exclusive_row_lock_when_the_caller_will_write_the_session(mock_db):
    mock_db.execute.return_value = _result(_row())

    sessions_crud.lock_live_session("session-id", mock_db, exclusive=True)

    statement = str(mock_db.execute.call_args.args[0].compile(dialect=postgresql.dialect()))
    assert "FOR UPDATE" in statement
    assert "FOR SHARE" not in statement


def test_session_lookup_lets_database_errors_reach_the_global_handler(mock_db):
    mock_db.execute.side_effect = SQLAlchemyError("database unavailable")
    with pytest.raises(SQLAlchemyError):
        sessions_crud.get_session_by_id("session-id", mock_db)


def test_create_session_stages_row_and_returns_dto(mock_db):
    session = sessions_schema.UserSessionsInternal(**vars(_row()))
    row = _row()
    with patch.object(sessions_models, "UsersSessions", return_value=row):
        result = sessions_crud.create_session(session, mock_db)
    assert result.id == "session-id"
    mock_db.add.assert_called_once_with(row)
    mock_db.flush.assert_called_once()
    mock_db.commit.assert_not_called()


def test_edit_session_stages_changes_and_returns_dto(mock_db):
    row = _row()
    mock_db.execute.return_value = _result(row)
    update = sessions_schema.UserSessionsInternal(**vars(_row(rotation_count=2)))
    result = sessions_crud.edit_session(update, mock_db)
    assert result.rotation_count == 2
    mock_db.flush.assert_called_once()
    mock_db.commit.assert_not_called()


def test_edit_missing_session_raises_not_found(mock_db):
    mock_db.execute.return_value = _result()
    with pytest.raises(core_exceptions.NotFoundError):
        sessions_crud.edit_session(sessions_schema.UserSessionsInternal(**vars(_row())), mock_db)


def test_token_exchange_claim_is_conditional_and_staged(mock_db):
    def operation(sid, db):
        return sessions_crud.claim_session_for_token_exchange(sid, "hashed", datetime.now(UTC), ["fed"], db)

    mock_db.execute.return_value = _result(rowcount=1)
    assert operation("session-id", mock_db) is True
    mock_db.execute.return_value = _result(rowcount=0)
    assert operation("session-id", mock_db) is False
    assert mock_db.commit.call_count == 0


def test_delete_session_stages_owned_session_deletion(mock_db):
    row = _row()
    mock_db.execute.return_value = _result(row)
    result = sessions_crud.delete_session("session-id", 7, mock_db)
    assert result.id == "session-id"
    mock_db.delete.assert_called_once_with(row)
    mock_db.flush.assert_called_once()
    mock_db.commit.assert_not_called()


def test_delete_session_hides_missing_or_unowned_row(mock_db):
    mock_db.execute.return_value = _result()
    with pytest.raises(core_exceptions.NotFoundError):
        sessions_crud.delete_session("session-id", 8, mock_db)


@pytest.mark.parametrize(
    "operation,args",
    [
        (sessions_crud.delete_sessions_by_family, ("family-id",)),
        (sessions_crud.delete_sessions_by_user, (7,)),
    ],
)
def test_bulk_deletes_stage_and_return_count(operation, args, mock_db):
    mock_db.execute.return_value = _result(rowcount=3)
    assert operation(*args, mock_db) == 3
    mock_db.commit.assert_not_called()


@pytest.mark.parametrize("purge", [sessions_crud.delete_idle_sessions, sessions_crud.delete_expired_sessions])
def test_a_purge_stages_the_delete_and_names_the_ended_sessions(purge, mock_db):
    mock_db.execute.return_value.all.return_value = [(7, "a"), (8, "b")]

    assert purge(datetime.now(UTC), 100, mock_db) == [(7, "a"), (8, "b")]
    assert "RETURNING" in str(mock_db.execute.call_args.args[0].compile(dialect=postgresql.dialect()))
    mock_db.commit.assert_not_called()


def test_csrf_hash_and_oauth_reference_updates_are_staged(mock_db):
    mock_db.execute.return_value = _result()
    sessions_crud.clear_oauth_state_reference("session-id", mock_db)
    mock_db.execute.return_value = _result(rowcount=1)
    sessions_crud.update_session_csrf_hash("session-id", "csrf-hash", mock_db)
    assert mock_db.execute.call_count == 2
    mock_db.commit.assert_not_called()


def test_existing_session_ids_names_only_the_sessions_that_still_exist():
    from tests._helpers.db import create_sqlite_session

    db = create_sqlite_session()
    now = datetime.now(UTC)
    for session_id in ("s1", "s2"):
        db.add(
            sessions_models.UsersSessions(
                id=session_id,
                user_id=7,
                refresh_token="hash",
                ip_address="127.0.0.1",
                device_type="PC",
                operating_system="Linux",
                operating_system_version="1",
                browser="Firefox",
                browser_version="1",
                created_at=now,
                last_activity_at=now,
                expires_at=now + timedelta(days=1),
                tokens_exchanged=True,
                token_family_id=session_id,
                rotation_count=0,
                client_type="web",
                auth_time=now,
                amr=["pwd"],
            )
        )
    db.commit()

    assert sessions_crud.get_existing_session_ids(["s1", "gone"], db) == {"s1"}
    assert sessions_crud.get_existing_session_ids([], db) == set()
    db.close()


def test_a_stored_session_reads_back_with_its_client_type():
    from tests._helpers.db import create_sqlite_session

    db = create_sqlite_session()
    sessions_crud.create_session(sessions_schema.UserSessionsInternal(**vars(_row(client_type="mobile"))), db)
    db.commit()

    assert sessions_crud.get_session_by_id("session-id", db).client_type is ClientType.MOBILE
    db.close()


def test_a_stored_session_reads_back_its_auth_time_and_methods():
    from tests._helpers.db import create_sqlite_session

    db = create_sqlite_session()
    auth_time = datetime(2026, 11, 10, 8, 0, tzinfo=UTC)
    sessions_crud.create_session(
        sessions_schema.UserSessionsInternal(**vars(_row(auth_time=auth_time, amr=["pwd", "otp", "mfa"]))), db
    )
    db.commit()

    stored = sessions_crud.get_session_by_id("session-id", db)
    assert stored.auth_time.replace(tzinfo=UTC) == auth_time
    assert stored.amr == ["pwd", "otp", "mfa"]
    db.close()


class TestUnexchangedSessions:
    """A session whose SSO token exchange has not happened is invisible, claimable once and purged at its expiry."""

    @staticmethod
    def _add(db, session_id, *, tokens_exchanged, expires_in=timedelta(days=1), created_offset=0):
        now = datetime.now(UTC)
        values = vars(_row(id=session_id, tokens_exchanged=tokens_exchanged))
        values.update(
            token_family_id=session_id,
            expires_at=now + expires_in,
            created_at=now + timedelta(seconds=created_offset),
            refresh_token="hashed" if tokens_exchanged else None,
        )
        db.add(sessions_models.UsersSessions(**values))
        db.flush()

    @pytest.fixture
    def db(self):
        from tests._helpers.db import create_sqlite_session

        session = create_sqlite_session()
        yield session
        session.close()

    def test_lists_and_counts_hide_unexchanged_sessions(self, db):
        self._add(db, "exchanged", tokens_exchanged=True)
        self._add(db, "pending", tokens_exchanged=False, created_offset=5)

        page = sessions_crud.get_user_sessions_page(7, db, limit=10, offset=0)

        assert [session.id for session in page] == ["exchanged"]
        assert sessions_crud.count_user_sessions(7, db) == 1

    def test_the_purge_removes_an_expired_unexchanged_session_and_keeps_a_live_one(self, db):
        self._add(db, "expired-pending", tokens_exchanged=False, expires_in=timedelta(minutes=-1))
        self._add(db, "live-pending", tokens_exchanged=False, expires_in=timedelta(minutes=5))

        removed = sessions_crud.delete_expired_sessions(datetime.now(UTC), 100, db)

        assert removed == [(7, "expired-pending")]
        assert sessions_crud.get_session_by_id("expired-pending", db) is None
        assert sessions_crud.get_session_by_id("live-pending", db) is not None

    def test_the_claim_sets_the_real_expiry(self, db):
        self._add(db, "pending", tokens_exchanged=False, expires_in=timedelta(minutes=5))
        real_expiry = datetime.now(UTC) + timedelta(days=30)

        assert sessions_crud.claim_session_for_token_exchange(
            "pending", "hashed", real_expiry, ["fed", "otp", "mfa"], db
        )

        db.expire_all()
        claimed = sessions_crud.get_session_by_id("pending", db)
        assert claimed is not None
        assert claimed.tokens_exchanged is True
        assert claimed.amr == ["fed", "otp", "mfa"]
        assert claimed.expires_at.replace(tzinfo=UTC) == real_expiry
