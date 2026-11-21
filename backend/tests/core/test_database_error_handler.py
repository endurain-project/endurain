"""Tests for how database errors that reach the API boundary map to problem documents."""

import logging

import psycopg.errors
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.exc import IntegrityError, OperationalError, SQLAlchemyError
from sqlalchemy.exc import TimeoutError as PoolTimeoutError

import core.exceptions as core_exceptions
import core.problem_details as core_problem_details

_STATEMENT = "INSERT INTO users (password) VALUES ('hunter2')"


def _client(error: Exception) -> TestClient:
    app = FastAPI()
    core_exceptions.register_exception_handlers(app)

    @app.get("/fail")
    def _fail():
        raise error

    return TestClient(app, raise_server_exceptions=False)


class TestUnavailable:
    @pytest.mark.parametrize(
        "error",
        [
            PoolTimeoutError("QueuePool limit of size 5 overflow 10 reached"),
            OperationalError(_STATEMENT, {}, psycopg.errors.LockNotAvailable("lock timeout")),
            OperationalError(_STATEMENT, {}, psycopg.errors.QueryCanceled("statement timeout")),
            OperationalError(_STATEMENT, {}, psycopg.OperationalError("server closed the connection unexpectedly")),
            OperationalError(_STATEMENT, {}, psycopg.errors.Error("connection is closed"), connection_invalidated=True),
            OperationalError(_STATEMENT, {}, psycopg.errors.ConnectionFailure("connection failure")),
            OperationalError(_STATEMENT, {}, psycopg.errors.AdminShutdown("terminating connection")),
            OperationalError(_STATEMENT, {}, psycopg.errors.CannotConnectNow("the database system is starting up")),
            OperationalError(_STATEMENT, {}, psycopg.errors.TooManyConnections("too many clients")),
        ],
        ids=[
            "pool-exhausted",
            "lock-timeout",
            "statement-timeout",
            "connection-lost",
            "connection-invalidated",
            "connection-failure",
            "server-shutdown",
            "server-starting",
            "too-many-connections",
        ],
    )
    def test_a_database_out_of_reach_is_a_503_with_retry_after(self, error):
        resp = _client(error).get("/fail")

        assert resp.status_code == 503
        assert resp.headers["content-type"].startswith(core_problem_details.PROBLEM_CONTENT_TYPE)
        assert resp.headers["retry-after"] == "5"
        assert resp.json()["type"] == "urn:endurain:error:service-unavailable"
        assert "hunter2" not in resp.text

    def test_an_unavailable_database_is_logged_as_a_warning(self, caplog):
        with caplog.at_level(logging.DEBUG):
            _client(PoolTimeoutError("pool")).get("/fail")

        records = [r for r in caplog.records if "Database" in r.getMessage()]
        assert records
        assert {r.levelno for r in records} == {logging.WARNING}

    def test_any_other_operational_error_stays_a_500(self):
        error = OperationalError(_STATEMENT, {}, psycopg.errors.DiskFull("could not extend file"))

        assert _client(error).get("/fail").status_code == 500

    def test_a_connection_the_server_ended_is_a_503(self, committed_sessions):
        import tests._helpers.database as test_database

        engine = test_database.database_engine(test_database.worker_database())
        try:
            with engine.connect() as victim, engine.connect() as killer:
                pid = victim.exec_driver_sql("SELECT pg_backend_pid()").scalar_one()
                killer.exec_driver_sql(f"SELECT pg_terminate_backend({int(pid)})")
                with pytest.raises(OperationalError) as lost:
                    victim.exec_driver_sql("SELECT 1")
        finally:
            engine.dispose()

        assert _client(lost.value).get("/fail").status_code == 503


class TestConflict:
    def test_a_commit_time_integrity_error_is_a_409(self):
        error = IntegrityError(_STATEMENT, {}, psycopg.errors.UniqueViolation("duplicate key"))

        resp = _client(error).get("/fail")

        assert resp.status_code == 409
        assert resp.headers["content-type"].startswith(core_problem_details.PROBLEM_CONTENT_TYPE)
        assert resp.json()["type"] == "urn:endurain:error:conflict"
        assert "hunter2" not in resp.text

    def test_a_conflict_is_not_logged_as_an_error(self, caplog):
        error = IntegrityError(_STATEMENT, {}, psycopg.errors.ForeignKeyViolation("fk"))

        with caplog.at_level(logging.DEBUG):
            _client(error).get("/fail")

        records = [r for r in caplog.records if "Database" in r.getMessage()]
        assert records
        assert max(r.levelno for r in records) == logging.WARNING


class TestOtherErrors:
    def test_a_generic_database_error_stays_an_opaque_500(self):
        assert _client(SQLAlchemyError(_STATEMENT)).get("/fail").status_code == 500
