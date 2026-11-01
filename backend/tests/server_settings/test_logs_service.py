"""Tests for the admin log viewer service."""

import json
from unittest.mock import patch

import pytest

import core.exceptions as core_exceptions
import modules.server_settings.logs_schema as logs_schema
import modules.server_settings.logs_service as logs_service


def _json_line(level: str, message: str, **extra) -> str:
    return json.dumps(
        {
            "timestamp": "2026-01-01T00:00:00+00:00",
            "level": level,
            "logger": "main_logger.x",
            "message": message,
            **extra,
        }
    )


@pytest.fixture
def logs_dir(tmp_path):
    with (
        patch("core.config.settings.LOGS_DIR", str(tmp_path)),
        patch("core.config.Settings.logs_viewer_enabled", True),
    ):
        yield tmp_path


def _write(logs_dir, lines: list[str]) -> None:
    (logs_dir / logs_service.LOG_FILE_NAME).write_text("".join(f"{line}\n" for line in lines))


class TestReadLogs:
    """Tests for read_logs."""

    def test_disabled_viewer_is_not_found(self, tmp_path):
        with (
            patch("core.config.settings.LOGS_DIR", str(tmp_path)),
            patch("core.config.Settings.logs_viewer_enabled", False),
            pytest.raises(core_exceptions.NotFoundError),
        ):
            logs_service.read_logs(10, None, None, None)

    def test_missing_file_returns_an_empty_page(self, logs_dir):
        page = logs_service.read_logs(10, None, None, None)
        assert page.entries == []
        assert page.cursor == 0

    def test_parses_json_lines(self, logs_dir):
        _write(logs_dir, [_json_line("INFO", "hello", request_id="r1", context={"user_id": 3})])
        entry = logs_service.read_logs(10, None, None, None).entries[0]
        assert (entry.level, entry.message, entry.request_id, entry.context) == ("INFO", "hello", "r1", {"user_id": 3})

    def test_parses_development_lines_and_folds_tracebacks(self, logs_dir):
        _write(
            logs_dir,
            [
                "2026-01-01 10:00:00,123 - main_logger.x - ERROR - [abc] - boom | a=1",
                "Traceback (most recent call last):",
                "ValueError: bad",
                "2026-01-01 10:00:01,000 - main_logger.x - INFO - [] - fine",
            ],
        )
        first, second = logs_service.read_logs(10, None, None, None).entries
        assert (first.level, first.request_id, first.message) == ("ERROR", "abc", "boom | a=1")
        assert first.exception == "Traceback (most recent call last):\nValueError: bad"
        assert second.request_id is None

    def test_returns_newest_entries_up_to_limit_oldest_first(self, logs_dir):
        _write(logs_dir, [_json_line("INFO", f"m{i}") for i in range(5)])
        page = logs_service.read_logs(2, None, None, None)
        assert [e.message for e in page.entries] == ["m3", "m4"]

    def test_filters_by_minimum_level(self, logs_dir):
        _write(logs_dir, [_json_line("DEBUG", "d"), _json_line("WARNING", "w"), _json_line("ERROR", "e")])
        page = logs_service.read_logs(10, logs_schema.LogLevel.WARNING, None, None)
        assert [e.message for e in page.entries] == ["w", "e"]

    def test_search_is_case_insensitive(self, logs_dir):
        _write(logs_dir, [_json_line("INFO", "Strava Sync done"), _json_line("INFO", "other")])
        page = logs_service.read_logs(10, None, "strava", None)
        assert [e.message for e in page.entries] == ["Strava Sync done"]

    def test_after_cursor_returns_only_new_entries(self, logs_dir):
        _write(logs_dir, [_json_line("INFO", "old")])
        cursor = logs_service.read_logs(10, None, None, None).cursor
        with (logs_dir / logs_service.LOG_FILE_NAME).open("a") as log_file:
            log_file.write(_json_line("INFO", "new") + "\n")
        page = logs_service.read_logs(10, None, None, cursor)
        assert [e.message for e in page.entries] == ["new"]
        assert logs_service.read_logs(10, None, None, page.cursor).entries == []

    def test_partial_last_line_waits_for_its_newline(self, logs_dir):
        path = logs_dir / logs_service.LOG_FILE_NAME
        path.write_text(_json_line("INFO", "done") + "\n" + '{"level": "INFO", "mess')
        page = logs_service.read_logs(10, None, None, None)
        assert [e.message for e in page.entries] == ["done"]
        assert page.cursor == len(_json_line("INFO", "done")) + 1

    def test_cursor_past_the_end_after_rotation_restarts_from_the_new_file(self, logs_dir):
        _write(logs_dir, [_json_line("INFO", "fresh")])
        page = logs_service.read_logs(10, None, None, 10_000_000)
        assert [e.message for e in page.entries] == ["fresh"]

    def test_large_file_is_read_from_a_line_boundary(self, logs_dir):
        with patch.object(logs_service, "MAX_READ_BYTES", 300):
            _write(logs_dir, [_json_line("INFO", f"message-{i}") for i in range(20)])
            page = logs_service.read_logs(100, None, None, None)
        assert page.entries
        assert page.entries[-1].message == "message-19"
        assert all(e.message.startswith("message-") for e in page.entries)


class TestGetLogFilePath:
    """Tests for get_log_file_path."""

    def test_returns_the_existing_file(self, logs_dir):
        _write(logs_dir, [_json_line("INFO", "x")])
        assert logs_service.get_log_file_path() == logs_dir / logs_service.LOG_FILE_NAME

    def test_missing_file_is_not_found(self, logs_dir):
        with pytest.raises(core_exceptions.NotFoundError):
            logs_service.get_log_file_path()

    def test_disabled_viewer_is_not_found(self, tmp_path):
        with patch("core.config.Settings.logs_viewer_enabled", False), pytest.raises(core_exceptions.NotFoundError):
            logs_service.get_log_file_path()


class TestClearLogs:
    """Tests for clear_logs."""

    def test_empties_the_file_and_removes_rotated_backups(self, logs_dir):
        _write(logs_dir, [_json_line("INFO", "old")])
        (logs_dir / "app.log.1").write_text("older")
        (logs_dir / "app.log.2").write_text("oldest")
        (logs_dir / "other.log").write_text("keep")

        logs_service.clear_logs(7)

        assert (logs_dir / logs_service.LOG_FILE_NAME).read_text() == ""
        assert not (logs_dir / "app.log.1").exists()
        assert not (logs_dir / "app.log.2").exists()
        assert (logs_dir / "other.log").exists()

    def test_records_who_cleared_the_logs(self, logs_dir):
        with patch.object(logs_service.logger, "warning") as warning:
            logs_service.clear_logs(7)
        assert warning.call_args.kwargs["extra"] == {"admin_id": 7}

    def test_missing_file_is_not_an_error(self, logs_dir):
        logs_service.clear_logs(7)

    def test_disabled_viewer_is_not_found(self, tmp_path):
        with patch("core.config.Settings.logs_viewer_enabled", False), pytest.raises(core_exceptions.NotFoundError):
            logs_service.clear_logs(7)


class TestLogsRouteScopes:
    """The log routes each require their own scope."""

    def test_reading_and_clearing_need_different_scopes(self):
        import modules.server_settings.logs_router as logs_router

        def scopes(path: str, method: str) -> set[str]:
            route = next(r for r in logs_router.router.routes if r.path == path and method in r.methods)
            return {scope for dep in route.dependant.dependencies for scope in dep.own_oauth_scopes or []}

        assert scopes("", "GET") == {"server_settings:logs"}
        assert scopes("/download", "GET") == {"server_settings:logs"}
        assert scopes("", "DELETE") == {"server_settings:logs_clear"}
