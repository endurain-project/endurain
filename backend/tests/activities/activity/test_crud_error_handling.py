"""Tests for activity CRUD database-error handling.

These cover the contract ``@handle_db_errors`` provides, which the file's 44
hand-written try/except blocks used to provide inconsistently: a failed statement
must roll the session back, must not leak SQL or bound parameters into the log,
and must surface as a 500.
"""

import logging
from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

import modules.activities.activity.crud as activities_crud

# A realistic SQLAlchemy error string: str() on these embeds the statement and
# the bound parameters, which is exactly what must not reach the log. Split into
# fragments so it is unmistakably fixture text rather than a constructed query.
_LEAKED_PARAMETER = "Morning ride with Sarah"
_LEAKED_STATEMENT = "SELECT * FROM activities WHERE name = %(name)s"
_DB_ERROR_TEXT = "connection lost [SQL: " + _LEAKED_STATEMENT + "] [parameters: {'name': '" + _LEAKED_PARAMETER + "'}]"


def _failing_db() -> MagicMock:
    """A session whose every statement raises, carrying SQL and parameters.

    Specced as a ``Session`` because the decorator locates the session with
    ``isinstance(value, Session)`` — a bare MagicMock is invisible to it, and the
    rollback assertions below would pass vacuously.
    """
    db = MagicMock(spec=Session)
    db.execute.side_effect = SQLAlchemyError(_DB_ERROR_TEXT)
    db.scalars.side_effect = db.execute.side_effect
    return db


class TestDatabaseErrorsBecome500:
    def test_read_failure_raises_500(self):
        with pytest.raises(HTTPException) as exc:
            activities_crud.get_all_activities(_failing_db())
        assert exc.value.status_code == 500

    def test_write_failure_raises_500(self):
        with pytest.raises(HTTPException) as exc:
            activities_crud.update_activity_location(1, "Lisbon", "Belem", "Portugal", _failing_db())
        assert exc.value.status_code == 500


class TestSessionIsRolledBack:
    """Postgres aborts the whole transaction after a failed statement.

    Without a rollback the session is poisoned: every later statement in the same
    request or bulk-import run fails with "current transaction is aborted". The
    hand-written handlers only rolled back in 8 of 44 functions.
    """

    def test_read_failure_rolls_back(self):
        db = _failing_db()
        with pytest.raises(HTTPException):
            activities_crud.get_all_activities(db)
        db.rollback.assert_called_once()

    def test_write_failure_rolls_back(self):
        db = _failing_db()
        with pytest.raises(HTTPException):
            activities_crud.update_activity_location(1, "Lisbon", "Belem", "Portugal", db)
        db.rollback.assert_called_once()


class TestNoSqlOrParametersInLogs:
    """OWASP A09: SQLAlchemy error strings embed the statement and its parameters.

    Activity names and descriptions are user content and routinely contain names
    and locations, so interpolating the error into the log leaked PII at every
    call site that did it.
    """

    def test_log_excludes_sql_and_parameters(self, caplog):
        with caplog.at_level(logging.ERROR), pytest.raises(HTTPException):
            activities_crud.get_all_activities(_failing_db())

        messages = " ".join(record.getMessage() for record in caplog.records)
        assert _LEAKED_PARAMETER not in messages
        assert _LEAKED_STATEMENT not in messages
        assert "parameters:" not in messages
        # The exception type is still identified for diagnosis.
        assert "SQLAlchemyError" in messages

    def test_response_detail_excludes_internals(self):
        with pytest.raises(HTTPException) as exc:
            activities_crud.get_all_activities(_failing_db())
        assert _LEAKED_STATEMENT not in exc.value.detail
        assert _LEAKED_PARAMETER not in exc.value.detail


class TestScheduledQueriesStillDegrade:
    """The backfill queries deliberately swallow rather than raise.

    A transient database error must not take the scheduler down, so these return
    an empty result and log. They were left undecorated on purpose — only their
    logging was corrected.
    """

    @pytest.mark.parametrize(
        "function",
        [
            activities_crud.get_activities_missing_location,
            activities_crud.get_activities_with_thumbnail,
            activities_crud.get_activities_without_thumbnail,
            activities_crud.get_activities_with_legacy_thumbnail_path,
        ],
    )
    def test_returns_empty_instead_of_raising(self, function):
        assert function(_failing_db()) == []

    @pytest.mark.parametrize(
        "function",
        [
            activities_crud.get_activities_missing_location,
            activities_crud.get_activities_with_thumbnail,
            activities_crud.get_activities_without_thumbnail,
            activities_crud.get_activities_with_legacy_thumbnail_path,
        ],
    )
    def test_swallowed_failures_also_keep_sql_out_of_logs(self, function, caplog):
        with caplog.at_level(logging.ERROR):
            function(_failing_db())

        messages = " ".join(record.getMessage() for record in caplog.records)
        assert _LEAKED_PARAMETER not in messages
        assert "parameters:" not in messages


class TestHttpExceptionsPassThrough:
    """A domain 404 must not be rewritten into a 500 by the decorator."""

    def test_delete_activity_404_survives(self):
        db = MagicMock(spec=Session)
        db.execute.return_value = MagicMock(rowcount=0)

        with pytest.raises(HTTPException) as exc:
            activities_crud.delete_activity(1, 2, db)

        assert exc.value.status_code == 404

    def test_delete_activity_404_still_rolls_back_the_staged_delete(self):
        # The 404 is raised after the DELETE is staged, and callers pass
        # commit=False; the rollback is kept explicitly for that reason.
        db = MagicMock(spec=Session)
        db.execute.return_value = MagicMock(rowcount=0)

        with pytest.raises(HTTPException):
            activities_crud.delete_activity(1, 2, db, commit=False)

        db.rollback.assert_called_once()
