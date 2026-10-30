"""Tests for staged auth-session persistence."""

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy.exc import SQLAlchemyError

import core.exceptions as core_exceptions
import modules.auth.sessions.crud as sessions_crud
import modules.auth.sessions.models as sessions_models
import modules.auth.sessions.schema as sessions_schema


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
    }
    values.update(updates)
    return SimpleNamespace(**values)


def _result(value=None, *, rowcount=1):
    result = MagicMock()
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


def test_session_lookup_lets_database_errors_reach_the_global_handler(mock_db):
    mock_db.execute.side_effect = SQLAlchemyError("database unavailable")
    with pytest.raises(SQLAlchemyError):
        sessions_crud.get_session_by_id("session-id", mock_db)


def test_create_session_stages_row_and_returns_dto(mock_db):
    session = sessions_schema.UsersSessionsInternal(**vars(_row()))
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
    update = sessions_schema.UsersSessionsInternal(**vars(_row(rotation_count=2)))
    result = sessions_crud.edit_session(update, mock_db)
    assert result.rotation_count == 2
    mock_db.flush.assert_called_once()
    mock_db.commit.assert_not_called()


def test_edit_missing_session_raises_not_found(mock_db):
    mock_db.execute.return_value = _result()
    with pytest.raises(core_exceptions.NotFoundError):
        sessions_crud.edit_session(sessions_schema.UsersSessionsInternal(**vars(_row())), mock_db)


def test_token_exchange_claim_is_conditional_and_staged(mock_db):
    operation = lambda sid, db: sessions_crud.claim_session_for_token_exchange(sid, "hashed", db)  # noqa: E731
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
        (sessions_crud.delete_idle_sessions, (datetime.now(UTC), 100)),
        (sessions_crud.delete_expired_sessions, (datetime.now(UTC), 100)),
        (sessions_crud.delete_sessions_by_family, ("family-id",)),
        (sessions_crud.delete_sessions_by_user, (7,)),
    ],
)
def test_bulk_deletes_stage_and_return_count(operation, args, mock_db):
    mock_db.execute.return_value = _result(rowcount=3)
    assert operation(*args, mock_db) == 3
    mock_db.commit.assert_not_called()


def test_csrf_hash_and_oauth_reference_updates_are_staged(mock_db):
    mock_db.execute.return_value = _result()
    sessions_crud.clear_oauth_state_reference("session-id", mock_db)
    mock_db.execute.return_value = _result(rowcount=1)
    sessions_crud.update_session_csrf_hash("session-id", "csrf-hash", mock_db)
    assert mock_db.execute.call_count == 2
    mock_db.commit.assert_not_called()
