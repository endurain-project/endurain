"""Tests for core.decorators module."""

from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

import core.decorators as core_decorators


class TestHandleDbErrors:
    """Tests for handle_db_errors decorator."""

    def test_function_succeeds(self):
        @core_decorators.handle_db_errors
        def my_func():
            return "success"

        assert my_func() == "success"

    def test_http_exception_re_raised(self):
        @core_decorators.handle_db_errors
        def my_func():
            raise HTTPException(status_code=400, detail="bad request")

        with pytest.raises(HTTPException) as exc_info:
            my_func()
        assert exc_info.value.status_code == 400

    def test_sqlalchemy_error_with_session_in_args(self):
        session = MagicMock(spec=Session)

        @core_decorators.handle_db_errors
        def my_func(session):
            msg = "DB down"
            raise SQLAlchemyError(msg)

        with (
            patch("core.decorators.logger") as mock_log,
            pytest.raises(HTTPException) as exc_info,
        ):
            my_func(session)

        assert exc_info.value.status_code == 500
        session.rollback.assert_called_once()
        assert len(mock_log.method_calls) == 1

    def test_sqlalchemy_error_with_session_in_kwargs(self):
        session = MagicMock(spec=Session)

        @core_decorators.handle_db_errors
        def my_func(some_session):
            raise SQLAlchemyError("DB down")

        with (
            patch("core.decorators.logger") as mock_log,
            pytest.raises(HTTPException) as exc_info,
        ):
            my_func(some_session=session)

        assert exc_info.value.status_code == 500
        session.rollback.assert_called_once()
        assert len(mock_log.method_calls) == 1

    def test_sqlalchemy_error_without_session(self):
        @core_decorators.handle_db_errors
        def my_func():
            raise SQLAlchemyError("DB down")

        with (
            patch("core.decorators.logger") as mock_log,
            pytest.raises(HTTPException) as exc_info,
        ):
            my_func()

        assert exc_info.value.status_code == 500
        assert len(mock_log.method_calls) == 1

    def test_integrity_error_with_session(self):
        session = MagicMock(spec=Session)

        @core_decorators.handle_db_errors
        def my_func(session):
            raise IntegrityError("stmt", {}, Exception("constraint violation"))

        with patch("core.decorators.logger"), pytest.raises(IntegrityError):
            my_func(session)

        session.rollback.assert_called_once()

    def test_rollback_failure(self):
        session = MagicMock(spec=Session)
        session.rollback.side_effect = RuntimeError("rollback failed")

        @core_decorators.handle_db_errors
        def my_func(session):
            raise SQLAlchemyError("DB down")

        with (
            patch("core.decorators.logger") as mock_log,
            pytest.raises(HTTPException) as exc_info,
        ):
            my_func(session)

        assert exc_info.value.status_code == 500
        assert len(mock_log.method_calls) == 2
        session.rollback.assert_called_once()
