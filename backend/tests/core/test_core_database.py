"""Tests for core.database module — get_db generator coverage."""

from unittest.mock import MagicMock, patch

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
