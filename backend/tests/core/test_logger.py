"""Tests for core.logger module."""

import json
import logging
import sys
from unittest.mock import MagicMock, patch

import core.logger as core_logger


class TestRequestIdFilter:
    """Tests for RequestIdFilter class."""

    def test_adds_request_id_to_record(self):
        filter_ = core_logger.RequestIdFilter()
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="/f.py",
            lineno=1,
            msg="msg",
            args=(),
            exc_info=None,
        )
        with patch("core.logger.core_middleware_request_id.get_request_id", return_value="req-abc"):
            result = filter_.filter(record)
        assert result is True
        assert record.request_id == "req-abc"


class TestJsonFormatter:
    """Tests for JsonFormatter class."""

    def test_format_basic(self):
        formatter = core_logger.JsonFormatter()
        record = logging.LogRecord(
            name="test_logger",
            level=logging.INFO,
            pathname="/f.py",
            lineno=1,
            msg="hello world",
            args=(),
            exc_info=None,
        )
        result = formatter.format(record)
        data = json.loads(result)
        assert data["level"] == "INFO"
        assert data["message"] == "hello world"
        assert data["logger"] == "test_logger"
        assert "request_id" not in data
        assert "exception" not in data
        assert "context" not in data
        assert "timestamp" in data

    def test_format_with_request_id(self):
        formatter = core_logger.JsonFormatter()
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="/f.py",
            lineno=1,
            msg="msg",
            args=(),
            exc_info=None,
        )
        record.request_id = "req-123"
        result = formatter.format(record)
        data = json.loads(result)
        assert data["request_id"] == "req-123"

    def test_format_with_exc_info(self):
        formatter = core_logger.JsonFormatter()
        try:
            raise ValueError("test error detail")
        except ValueError:
            record = logging.LogRecord(
                name="test",
                level=logging.ERROR,
                pathname="/f.py",
                lineno=1,
                msg="error occurred",
                args=(),
                exc_info=sys.exc_info(),
            )
        result = formatter.format(record)
        data = json.loads(result)
        assert "exception" in data
        assert "ValueError" in data["exception"]
        assert "test error detail" in data["exception"]

    def test_format_with_context(self):
        formatter = core_logger.JsonFormatter()
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="/f.py",
            lineno=1,
            msg="msg",
            args=(),
            exc_info=None,
        )
        record.user_id = 42
        record.action = "login"
        result = formatter.format(record)
        data = json.loads(result)
        assert data["context"]["user_id"] == 42
        assert data["context"]["action"] == "login"


class TestDevFormatter:
    """Tests for _DevFormatter class."""

    def test_format_basic(self):
        formatter = core_logger._DevFormatter()
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="/f.py",
            lineno=1,
            msg="hello",
            args=(),
            exc_info=None,
        )
        record.request_id = ""
        result = formatter.format(record)
        assert "hello" in result
        assert "INFO" in result
        assert "test" in result

    def test_format_with_context(self):
        formatter = core_logger._DevFormatter()
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="/f.py",
            lineno=1,
            msg="hello",
            args=(),
            exc_info=None,
        )
        record.request_id = ""
        record.user_id = 42
        result = formatter.format(record)
        assert "hello" in result
        assert "user_id=42" in result


class TestBuildHandlers:
    """Tests for _build_handlers function."""

    def test_production_returns_stream_handler(self):
        with (
            patch("core.config.settings.ENVIRONMENT", "production"),
            patch("core.config.settings.LOGS_DIR", ""),
        ):
            handlers = core_logger._build_handlers(logging.INFO)
        assert len(handlers) == 1
        handler = handlers[0]
        assert isinstance(handler, logging.StreamHandler)
        assert isinstance(handler.formatter, core_logger.JsonFormatter)
        assert handler.level == logging.INFO

    def test_demo_returns_stream_handler(self):
        with (
            patch("core.config.settings.ENVIRONMENT", "demo"),
            patch("core.config.settings.LOGS_DIR", ""),
        ):
            handlers = core_logger._build_handlers(logging.WARNING)
        assert len(handlers) == 1
        handler = handlers[0]
        assert isinstance(handler, logging.StreamHandler)
        assert isinstance(handler.formatter, core_logger.JsonFormatter)

    def test_development_returns_file_handler_and_console_mirror(self, tmp_path):
        with (
            patch("core.config.settings.ENVIRONMENT", "development"),
            patch("core.config.settings.LOGS_DIR", str(tmp_path)),
        ):
            handlers = core_logger._build_handlers(logging.DEBUG)
        assert len(handlers) == 2
        file_handler, console_handler = handlers
        assert isinstance(file_handler, logging.FileHandler)
        assert isinstance(file_handler.formatter, core_logger._DevFormatter)
        assert file_handler.level == logging.DEBUG
        assert isinstance(console_handler, logging.StreamHandler)
        assert any(isinstance(f, core_logger.ConsoleMirrorFilter) for f in console_handler.filters)


class TestReplaceHandlers:
    """Tests for _replace_handlers function."""

    def test_replaces_handlers(self):
        old_handler = MagicMock(spec=logging.Handler)
        new_handler = MagicMock(spec=logging.Handler)
        logger = logging.Logger("test_replace")
        logger.addHandler(old_handler)

        core_logger._replace_handlers((logger,), [new_handler])

        assert logger.handlers == [new_handler]
        assert logger.propagate is False

    def test_closes_old_handlers(self):
        old_handler = MagicMock(spec=logging.Handler)
        new_handler = MagicMock(spec=logging.Handler)
        logger = logging.Logger("test_close")
        logger.addHandler(old_handler)

        core_logger._replace_handlers((logger,), [new_handler])

        old_handler.close.assert_called_once()


class TestSetupMainLogger:
    """Tests for setup_main_logger function."""

    def test_returns_logger(self, tmp_path):
        with (
            patch("core.config.settings.ENVIRONMENT", "development"),
            patch("core.config.settings.LOG_LEVEL", "debug"),
            patch("core.config.settings.LOGS_DIR", str(tmp_path)),
        ):
            logger = core_logger.setup_main_logger()
        assert isinstance(logger, logging.Logger)
        assert logger.name == "main_logger"

    def test_logger_has_correct_level(self, tmp_path):
        with (
            patch("core.config.settings.ENVIRONMENT", "development"),
            patch("core.config.settings.LOG_LEVEL", "error"),
            patch("core.config.settings.LOGS_DIR", str(tmp_path)),
        ):
            logger = core_logger.setup_main_logger()
        assert logger.level == logging.ERROR

    def test_default_level_for_invalid_config(self, tmp_path):
        with (
            patch("core.config.settings.ENVIRONMENT", "development"),
            patch("core.config.settings.LOG_LEVEL", "invalid_level"),
            patch("core.config.settings.LOGS_DIR", str(tmp_path)),
        ):
            logger = core_logger.setup_main_logger()
        assert logger.level == logging.WARNING

    def test_safeuploads_audit_logger_propagates(self, tmp_path):
        with (
            patch("core.config.settings.ENVIRONMENT", "development"),
            patch("core.config.settings.LOG_LEVEL", "warning"),
            patch("core.config.settings.LOGS_DIR", str(tmp_path)),
        ):
            core_logger.setup_main_logger()
        assert logging.getLogger("safeuploads.audit").propagate is True


class TestGetLogger:
    """Tests for get_logger function."""

    def test_returns_root_logger_without_name(self):
        assert core_logger.get_logger().name == core_logger.ROOT_LOGGER_NAME

    def test_returns_child_of_root_logger(self):
        logger = core_logger.get_logger("modules.activities.activity.crud")
        assert logger.name == f"{core_logger.ROOT_LOGGER_NAME}.modules.activities.activity.crud"
        assert logger.parent is not None

    def test_does_not_double_prefix(self):
        name = f"{core_logger.ROOT_LOGGER_NAME}.already.prefixed"
        assert core_logger.get_logger(name).name == name

    def test_root_name_returns_root(self):
        assert core_logger.get_logger(core_logger.ROOT_LOGGER_NAME).name == core_logger.ROOT_LOGGER_NAME


class TestContext:
    """Tests for the context helper."""

    def test_drops_none_values(self):
        assert core_logger.context(activity_id=7, gear_id=None) == {"activity_id": 7}

    def test_namespaces_reserved_keys(self):
        assert core_logger.context(module="strava") == {"ctx_module": "strava"}

    def test_console_flag(self):
        assert core_logger.context(console=True) == {core_logger.CONSOLE_FIELD: True}

    def test_console_absent_by_default(self):
        assert core_logger.CONSOLE_FIELD not in core_logger.context(user_id=1)


class TestConsoleMirrorFilter:
    """Tests for ConsoleMirrorFilter class."""

    def _record(self, **extra):
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="/f.py",
            lineno=1,
            msg="msg",
            args=(),
            exc_info=None,
        )
        for key, value in extra.items():
            setattr(record, key, value)
        return record

    def test_passes_flagged_record(self):
        assert core_logger.ConsoleMirrorFilter().filter(self._record(console=True)) is True

    def test_rejects_unflagged_record(self):
        assert core_logger.ConsoleMirrorFilter().filter(self._record()) is False


class TestEndToEnd:
    """A record logged through a module logger reaches the configured handlers."""

    def test_module_logger_record_carries_name_and_context(self, tmp_path):
        with (
            patch("core.config.settings.ENVIRONMENT", "production"),
            patch("core.config.settings.LOG_LEVEL", "debug"),
            patch("core.config.settings.LOGS_DIR", str(tmp_path)),
        ):
            core_logger.setup_main_logger()

        logger = core_logger.get_logger("modules.activities.activity.crud")
        records: list[logging.LogRecord] = []

        class _Capture(logging.Handler):
            def emit(self, record: logging.LogRecord) -> None:
                records.append(record)

        capture = _Capture()
        logging.getLogger(core_logger.ROOT_LOGGER_NAME).addHandler(capture)
        try:
            logger.warning("stored", extra=core_logger.context(activity_id=42, gear_id=None))
        finally:
            logging.getLogger(core_logger.ROOT_LOGGER_NAME).removeHandler(capture)

        assert len(records) == 1
        record = records[0]
        assert record.name == f"{core_logger.ROOT_LOGGER_NAME}.modules.activities.activity.crud"
        assert record.levelno == logging.WARNING
        assert record.activity_id == 42
        assert not hasattr(record, "gear_id")
        assert json.loads(core_logger.JsonFormatter().format(record))["context"] == {"activity_id": 42}
