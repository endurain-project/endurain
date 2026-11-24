"""Tests for core.database: pool and connect options, the connection budget, batched purges and ``get_db``."""

import uuid

import pytest
from sqlalchemy import delete, func, select, update

import core.database as core_database
import modules.users.users.models as users_models
from tests._factories.users import make_user


class TestGetDb:
    """``get_db`` yields a session on the database and owns its end."""

    def test_the_session_is_closed_when_the_request_ends(self, committed_sessions):
        gen = core_database.get_db()
        session = next(gen)
        session.execute(select(1))
        assert session.in_transaction()

        with pytest.raises(StopIteration):
            next(gen)

        assert not session.in_transaction()

    def test_staged_work_is_rolled_back_when_the_request_fails(self, committed_sessions):
        gen = core_database.get_db()
        session = next(gen)
        user = make_user(session)

        with pytest.raises(RuntimeError, match="db error"):
            gen.throw(RuntimeError("db error"))

        assert not session.in_transaction()
        with committed_sessions() as other:
            assert other.get(users_models.Users, user.id) is None

    def test_work_committed_before_the_request_failed_is_kept(self, committed_sessions):
        gen = core_database.get_db()
        session = next(gen)
        user = make_user(session)
        session.commit()

        with pytest.raises(RuntimeError):
            gen.throw(RuntimeError("late failure"))

        with committed_sessions() as other:
            assert other.get(users_models.Users, user.id) is not None


class TestEngineErrorRedaction:
    """A database error string must not carry the bound parameters of the failing statement."""

    def test_the_engine_hides_statement_parameters(self):
        assert core_database.engine.hide_parameters is True


class TestPoolProcesses:
    """The durable-jobs worker is a process of its own, with a pool of its own."""

    def test_the_api_processes_alone_without_durable_jobs(self):
        assert core_database.pool_processes(web_workers=2, jobs_enabled=False) == 2

    def test_a_worker_is_counted_when_durable_jobs_are_enabled(self):
        assert core_database.pool_processes(web_workers=2, jobs_enabled=True) == 3


class TestPoolOptions:
    """Pool size and overflow come from the environment, with the previous values as defaults."""

    def test_defaults_keep_the_historical_pool(self):
        assert core_database._pool_options({}) == {
            "pool_size": 20,
            "max_overflow": 40,
            "pool_timeout": 30,
        }

    def test_the_environment_overrides_them(self):
        env = {"DB_POOL_SIZE": "5", "DB_MAX_OVERFLOW": "0", "DB_POOL_TIMEOUT_SECONDS": "10"}

        assert core_database._pool_options(env) == {"pool_size": 5, "max_overflow": 0, "pool_timeout": 10}

    @pytest.mark.parametrize(
        ("name", "value"),
        [
            ("DB_POOL_SIZE", "0"),
            ("DB_POOL_SIZE", "-3"),
            ("DB_POOL_SIZE", "many"),
            ("DB_MAX_OVERFLOW", "-1"),
            ("DB_POOL_TIMEOUT_SECONDS", "0"),
            ("DB_POOL_TIMEOUT_SECONDS", "-1"),
            ("DB_POOL_TIMEOUT_SECONDS", "soon"),
        ],
    )
    def test_an_unusable_value_falls_back_to_the_default(self, name, value):
        options = core_database._pool_options({name: value})

        assert options == {"pool_size": 20, "max_overflow": 40, "pool_timeout": 30}


class TestConnectOptions:
    """Session options sent to PostgreSQL on connect."""

    def test_defaults_pin_utc_and_the_lock_timeout_and_leave_statements_unbounded(self):
        options = core_database._connect_args({})["options"]

        assert options == "-c timezone=utc -c lock_timeout=30s"

    def test_the_lock_timeout_is_read_from_the_environment(self):
        options = core_database._connect_args({"DB_LOCK_TIMEOUT_SECONDS": "5"})["options"]

        assert options == "-c timezone=utc -c lock_timeout=5s"

    @pytest.mark.parametrize("value", ["0", "-5", "soon", ""])
    def test_an_unusable_lock_timeout_falls_back_to_the_default(self, value):
        options = core_database._connect_args({"DB_LOCK_TIMEOUT_SECONDS": value})["options"]

        assert options == "-c timezone=utc -c lock_timeout=30s"

    def test_a_statement_timeout_is_added_when_set(self):
        options = core_database._connect_args({"DB_STATEMENT_TIMEOUT_SECONDS": "120"})["options"]

        assert options == "-c timezone=utc -c lock_timeout=30s -c statement_timeout=120s"

    @pytest.mark.parametrize("value", ["0", "-5", "soon", ""])
    def test_a_disabled_or_unusable_statement_timeout_adds_nothing(self, value):
        options = core_database._connect_args({"DB_STATEMENT_TIMEOUT_SECONDS": value})["options"]

        assert "statement_timeout" not in options

    def test_tls_is_opt_in(self):
        assert "sslmode" not in core_database._connect_args({})
        assert core_database._connect_args({"DB_SSLMODE": " Require "})["sslmode"] == "require"


class TestConnectionBudgetWarning:
    """The pool can hold more connections than PostgreSQL allows; startup says so instead of failing later."""

    def test_a_budget_within_the_limit_has_no_warning(self):
        assert core_database.connection_budget_warning(20, 40, 1, max_connections=100, reserved=3) is None

    def test_a_single_process_at_the_default_pool_fits_the_default_limit(self):
        assert core_database.connection_budget_warning(20, 40, 1, max_connections=100, reserved=3) is None

    def test_several_workers_that_exceed_the_limit_are_reported(self):
        warning = core_database.connection_budget_warning(20, 40, 2, max_connections=100, reserved=3)

        assert warning is not None
        assert "120" in warning and "97" in warning
        assert "DB_POOL_SIZE" in warning and "DB_MAX_OVERFLOW" in warning

    def test_the_connections_reserved_for_superusers_are_not_counted_as_available(self):
        assert core_database.connection_budget_warning(20, 40, 1, max_connections=62, reserved=3) is not None
        assert core_database.connection_budget_warning(20, 40, 1, max_connections=63, reserved=3) is None

    def test_the_warning_says_other_processes_add_to_the_total(self):
        warning = core_database.connection_budget_warning(20, 40, 2, max_connections=100, reserved=3)

        assert "replica" in warning and "worker" in warning

    def test_the_server_limits_are_read_and_a_warning_is_logged(self, committed_sessions, caplog):
        with caplog.at_level("WARNING"):
            core_database.check_connection_budget(1000)

        assert "database connections" in caplog.text

    def test_a_fitting_budget_logs_nothing(self, committed_sessions, caplog):
        with caplog.at_level("WARNING"):
            core_database.check_connection_budget(1)

        assert caplog.text == ""


class TestDeleteInBatches:
    """A maintenance purge runs one bounded batch per transaction, so it never holds a long lock."""

    def _users(self, committed_sessions, count: int) -> list[uuid.UUID]:
        with committed_sessions() as db:
            ids = [make_user(db).id for _ in range(count)]
            db.commit()
        return ids

    def _remaining(self, committed_sessions, ids: list[uuid.UUID]) -> int:
        with committed_sessions() as db:
            return db.scalar(select(func.count()).select_from(users_models.Users).where(users_models.Users.id.in_(ids)))

    def test_full_batches_continue_and_a_short_one_ends_the_purge(self, committed_sessions):
        ids = self._users(committed_sessions, 3)
        size = core_database.PURGE_BATCH_SIZE
        counts = iter([size, size, 3])
        limits: list[int] = []
        remaining = iter(ids)

        with committed_sessions() as db:

            def stage_batch(limit: int) -> int:
                limits.append(limit)
                db.execute(delete(users_models.Users).where(users_models.Users.id == next(remaining)))
                return next(counts)

            assert core_database.delete_in_batches(stage_batch, db) == 2 * size + 3

        assert limits == [size] * 3
        assert self._remaining(committed_sessions, ids) == 0

    def test_each_batch_is_committed_before_the_next_is_staged(self, committed_sessions):
        ids = self._users(committed_sessions, 2)
        size = core_database.PURGE_BATCH_SIZE
        visible_to_others: list[int] = []
        batches = iter([size, 0])
        victims = iter(ids)

        with committed_sessions() as db:

            def stage_batch(limit: int) -> int:
                visible_to_others.append(self._remaining(committed_sessions, ids))
                db.execute(delete(users_models.Users).where(users_models.Users.id == next(victims)))
                return next(batches)

            core_database.delete_in_batches(stage_batch, db)

        assert visible_to_others == [2, 1]
        assert self._remaining(committed_sessions, ids) == 0

    def test_nothing_to_delete_still_ends_the_transaction(self, committed_sessions):
        with committed_sessions() as db:
            db.execute(select(1))

            assert core_database.delete_in_batches(lambda limit: 0, db) == 0

            assert not db.in_transaction()


class TestRowcount:
    """rowcount executes a DML statement and returns how many rows it matched."""

    @pytest.fixture
    def user_id(self, db):
        return make_user(db).id

    def test_an_update_returns_the_rows_it_matched(self, db, user_id):
        stmt = update(users_models.Users).where(users_models.Users.id == user_id).values(height=180)

        assert core_database.rowcount(db, stmt) == 1

    def test_a_delete_that_matches_nothing_returns_zero(self, db, user_id):
        stmt = delete(users_models.Users).where(users_models.Users.id == uuid.uuid4())

        assert core_database.rowcount(db, stmt) == 0

    def test_a_statement_that_returns_rows_is_refused(self, db, user_id):
        with pytest.raises(TypeError):
            core_database.rowcount(db, select(users_models.Users))
