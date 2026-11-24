"""Reading the application log file for the admin log viewer."""

import json
from pathlib import Path

import pytest

import core.config as core_config
import core.exceptions as core_exceptions
import modules.server_settings.logs_schema as logs_schema
import modules.server_settings.logs_service as logs_service


def _json_line(level: str, message: str, **extra: object) -> str:
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
def logs_dir(tmp_path, monkeypatch) -> Path:
    """An empty log directory the viewer reads."""
    monkeypatch.setattr(core_config.settings, "LOGS_DIR", str(tmp_path))
    return tmp_path


def _write(logs_dir: Path, lines: list[str]) -> None:
    (logs_dir / logs_service.LOG_FILE_NAME).write_text("".join(f"{line}\n" for line in lines))


class TestReadLogs:
    def test_a_disabled_viewer_is_not_found(self, logs_dir, monkeypatch):
        monkeypatch.setattr(core_config.settings, "ENVIRONMENT", "demo")

        with pytest.raises(core_exceptions.NotFoundError):
            logs_service.read_logs(10, None, None, None)

    def test_a_missing_file_returns_an_empty_page(self, logs_dir):
        page = logs_service.read_logs(10, None, None, None)

        assert page.items == []
        assert page.next_cursor == "0"

    def test_json_lines_are_parsed(self, logs_dir):
        _write(logs_dir, [_json_line("INFO", "hello", request_id="r1", context={"user_id": 3})])

        entry = logs_service.read_logs(10, None, None, None).items[0]

        assert (entry.level, entry.message, entry.request_id, entry.context) == ("INFO", "hello", "r1", {"user_id": 3})

    def test_development_lines_are_parsed_and_tracebacks_fold_into_their_record(self, logs_dir):
        _write(
            logs_dir,
            [
                "2026-01-01 10:00:00,123 - main_logger.x - ERROR - [abc] - boom | a=1",
                "Traceback (most recent call last):",
                "ValueError: bad",
                "2026-01-01 10:00:01,000 - main_logger.x - INFO - [] - fine",
            ],
        )

        first, second = logs_service.read_logs(10, None, None, None).items

        assert (first.level, first.request_id, first.message) == ("ERROR", "abc", "boom | a=1")
        assert first.exception == "Traceback (most recent call last):\nValueError: bad"
        assert second.request_id is None

    def test_a_line_that_starts_no_record_before_the_first_one_is_dropped(self, logs_dir):
        _write(logs_dir, ["stray continuation line", _json_line("INFO", "first"), '{"no": "level"}'])

        page = logs_service.read_logs(10, None, None, None)

        assert [e.message for e in page.items] == ["first"]
        assert page.items[0].exception == '{"no": "level"}'

    def test_blank_lines_are_skipped_and_a_broken_json_line_folds_into_the_record_above(self, logs_dir):
        _write(
            logs_dir, [_json_line("INFO", "first"), "", "   ", '{"level": "INFO", "mess', _json_line("INFO", "last")]
        )

        page = logs_service.read_logs(10, None, None, None)

        assert [e.message for e in page.items] == ["first", "last"]
        assert page.items[0].exception == '{"level": "INFO", "mess'

    def test_the_newest_entries_up_to_the_limit_are_returned_oldest_first(self, logs_dir):
        _write(logs_dir, [_json_line("INFO", f"m{i}") for i in range(5)])

        page = logs_service.read_logs(2, None, None, None)

        assert [e.message for e in page.items] == ["m3", "m4"]

    def test_the_minimum_level_filters_out_lower_ones(self, logs_dir):
        _write(logs_dir, [_json_line("DEBUG", "d"), _json_line("WARNING", "w"), _json_line("ERROR", "e")])

        page = logs_service.read_logs(10, logs_schema.LogLevel.WARNING, None, None)

        assert [e.message for e in page.items] == ["w", "e"]

    def test_the_text_filter_ignores_case_and_looks_in_the_message_logger_request_id_and_exception(self, logs_dir):
        _write(
            logs_dir,
            [
                _json_line("INFO", "Strava Sync done"),
                _json_line("INFO", "other", request_id="REQ-strava"),
                _json_line("INFO", "failed", exception="StravaError: nope"),
                _json_line("INFO", "unrelated"),
            ],
        )

        page = logs_service.read_logs(10, None, "strava", None)

        assert [e.message for e in page.items] == ["Strava Sync done", "other", "failed"]

    def test_a_cursor_returns_only_what_was_written_since(self, logs_dir):
        _write(logs_dir, [_json_line("INFO", "old")])
        cursor = int(logs_service.read_logs(10, None, None, None).next_cursor)
        with (logs_dir / logs_service.LOG_FILE_NAME).open("a") as log_file:
            log_file.write(_json_line("INFO", "new") + "\n")

        page = logs_service.read_logs(10, None, None, cursor)

        assert [e.message for e in page.items] == ["new"]
        assert logs_service.read_logs(10, None, None, int(page.next_cursor)).items == []

    def test_a_partial_last_line_waits_for_its_newline(self, logs_dir):
        path = logs_dir / logs_service.LOG_FILE_NAME
        path.write_text(_json_line("INFO", "done") + "\n" + '{"level": "INFO", "mess')

        page = logs_service.read_logs(10, None, None, None)

        assert [e.message for e in page.items] == ["done"]
        assert page.next_cursor == str(len(_json_line("INFO", "done")) + 1)

    def test_a_cursor_past_the_end_after_rotation_restarts_from_the_new_file(self, logs_dir):
        _write(logs_dir, [_json_line("INFO", "fresh")])

        page = logs_service.read_logs(10, None, None, 10_000_000)

        assert [e.message for e in page.items] == ["fresh"]

    def test_a_file_larger_than_the_read_window_is_read_from_a_line_boundary(self, logs_dir):
        padding = "x" * 1000
        count = logs_service.MAX_READ_BYTES // 1000 + 200
        _write(logs_dir, [_json_line("INFO", f"message-{i}-{padding}") for i in range(count)])

        page = logs_service.read_logs(100_000, None, None, None)

        assert page.items[-1].message.startswith(f"message-{count - 1}-")
        assert all(e.message.startswith("message-") for e in page.items)
        assert len(page.items) < count

    def test_a_cursor_further_back_than_the_read_window_reads_the_newest_window(self, logs_dir):
        padding = "x" * 1000
        count = logs_service.MAX_READ_BYTES // 1000 + 200
        _write(logs_dir, [_json_line("INFO", f"message-{i}-{padding}") for i in range(count)])

        page = logs_service.read_logs(100_000, None, None, 0)

        assert page.items[-1].message.startswith(f"message-{count - 1}-")
        assert len(page.items) < count


class TestGetLogFilePath:
    def test_a_disabled_viewer_is_not_found(self, logs_dir, monkeypatch):
        _write(logs_dir, [_json_line("INFO", "x")])
        monkeypatch.setattr(core_config.settings, "ENVIRONMENT", "demo")

        with pytest.raises(core_exceptions.NotFoundError):
            logs_service.get_log_file_path()

    def test_a_missing_file_is_not_found(self, logs_dir):
        with pytest.raises(core_exceptions.NotFoundError):
            logs_service.get_log_file_path()
