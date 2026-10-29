"""Tests for core.database module — get_db generator coverage."""

from unittest.mock import MagicMock, call, patch

import pytest

import core.database as core_database


class TestGetDb:
    """Tests for get_db generator."""

    def test_get_db_cleans_up(self):
        """get_db closes session after yield (finally block)."""
        mock_db = MagicMock()
        with patch("core.database.SessionLocal", return_value=mock_db):
            gen = core_database.get_db()
            db = next(gen)
            assert db is mock_db
            with pytest.raises(StopIteration):
                next(gen)
            mock_db.close.assert_called_once()
            mock_db.rollback.assert_not_called()

    def test_get_db_rolls_back_on_exception(self):
        """get_db rolls back and re-raises on exception (lines 118-120)."""
        mock_db = MagicMock()
        with patch("core.database.SessionLocal", return_value=mock_db):
            gen = core_database.get_db()
            db = next(gen)
            assert db is mock_db
            with pytest.raises(RuntimeError, match="db error"):
                gen.throw(RuntimeError("db error"))
            mock_db.rollback.assert_called_once()
            mock_db.close.assert_called_once()


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
        assert core_database._pool_options({}) == {"pool_size": 20, "max_overflow": 40}

    def test_the_environment_overrides_them(self):
        env = {"DB_POOL_SIZE": "5", "DB_MAX_OVERFLOW": "0"}

        assert core_database._pool_options(env) == {"pool_size": 5, "max_overflow": 0}

    @pytest.mark.parametrize(
        ("name", "value"),
        [("DB_POOL_SIZE", "0"), ("DB_POOL_SIZE", "-3"), ("DB_POOL_SIZE", "many"), ("DB_MAX_OVERFLOW", "-1")],
    )
    def test_an_unusable_value_falls_back_to_the_default(self, name, value):
        options = core_database._pool_options({name: value})

        assert options == {"pool_size": 20, "max_overflow": 40}


class TestConnectOptions:
    """Session options sent to PostgreSQL on connect."""

    def test_defaults_pin_utc_and_the_lock_timeout_and_leave_statements_unbounded(self):
        options = core_database._connect_args({})["options"]

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

    def test_the_server_limits_are_read_and_a_warning_is_logged(self, caplog):
        connection = MagicMock()
        connection.execute.return_value.scalar_one.side_effect = ["100", "3"]
        engine = MagicMock()
        engine.connect.return_value.__enter__.return_value = connection

        with (
            patch.object(core_database, "engine", engine),
            patch.object(core_database, "_POOL_OPTIONS", {"pool_size": 20, "max_overflow": 40}),
            caplog.at_level("WARNING"),
        ):
            core_database.check_connection_budget(2)

        assert "database connections" in caplog.text

    def test_a_fitting_budget_logs_nothing(self, caplog):
        connection = MagicMock()
        connection.execute.return_value.scalar_one.side_effect = ["200", "3"]
        engine = MagicMock()
        engine.connect.return_value.__enter__.return_value = connection

        with (
            patch.object(core_database, "engine", engine),
            patch.object(core_database, "_POOL_OPTIONS", {"pool_size": 20, "max_overflow": 40}),
            caplog.at_level("WARNING"),
        ):
            core_database.check_connection_budget(2)

        assert caplog.text == ""


class TestDeleteInBatches:
    """A maintenance purge runs one bounded batch per transaction, so it never holds a long lock."""

    def test_full_batches_continue_and_a_short_one_ends_the_purge(self):
        db = MagicMock()
        size = core_database.PURGE_BATCH_SIZE
        stage_batch = MagicMock(side_effect=[size, size, 3])

        assert core_database.delete_in_batches(stage_batch, db) == 2 * size + 3
        assert stage_batch.call_args_list == [call(size)] * 3
        assert db.commit.call_count == 3

    def test_nothing_to_delete_still_ends_the_transaction(self):
        db = MagicMock()

        assert core_database.delete_in_batches(MagicMock(return_value=0), db) == 0
        db.commit.assert_called_once()

    def test_each_batch_is_committed_before_the_next_is_staged(self):
        db = MagicMock()
        order: list[str] = []
        db.commit.side_effect = lambda: order.append("commit")

        def stage_batch(limit):
            order.append("stage")
            return limit if len(order) < 2 else 0

        core_database.delete_in_batches(stage_batch, db)

        assert order == ["stage", "commit", "stage", "commit"]
