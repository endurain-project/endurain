"""Reads the application log file for the admin log viewer.

The log is ``{LOGS_DIR}/app.log``: JSON lines in production, plain text in
development. Only a deployment where one process writes the file can offer it
(see ``Settings.logs_viewer_enabled``); everything here refuses otherwise.
"""

import json
import logging
import re
from pathlib import Path

import core.config as core_config
import core.exceptions as core_exceptions
import core.logger as core_logger
import modules.server_settings.logs_schema as logs_schema

logger = core_logger.get_logger(__name__)

LOG_FILE_NAME = "app.log"

#: Most bytes read from the end of the file in one call, so a request never loads a whole log.
MAX_READ_BYTES = 2 * 1024 * 1024

#: Shape of a development-format line: ``<time> - <logger> - <LEVEL> - [<request id>] - <message>``.
_DEV_LINE = re.compile(
    r"^(?P<timestamp>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2},\d{3}) - (?P<logger>.*?) - "
    r"(?P<level>[A-Z]+) - \[(?P<request_id>[^\]]*)\] - (?P<message>.*)$"
)

_LEVEL_NUMBERS = logging.getLevelNamesMapping()


def get_logs_status() -> logs_schema.LogsStatus:
    """Report whether the log viewer is available.

    Returns:
        The status, enabled unless this is the demo or a multi-process deployment.
    """
    return logs_schema.LogsStatus(enabled=core_config.settings.logs_viewer_enabled)


def get_log_file_path() -> Path:
    """Return the path of the log file for download.

    Returns:
        The existing application log file.

    Raises:
        NotFoundError: If the viewer is disabled or no log file has been written.
    """
    if not core_config.settings.logs_viewer_enabled:
        raise core_exceptions.NotFoundError("The log viewer is not available")
    path = Path(core_config.settings.LOGS_DIR) / LOG_FILE_NAME
    if not path.is_file():
        raise core_exceptions.NotFoundError("No log file has been written yet")
    return path


def read_logs(
    limit: int,
    min_level: logs_schema.LogLevel | None,
    search: str | None,
    after: int | None,
) -> logs_schema.LogPage:
    """Read records from the end of the log file.

    Without ``after`` this returns the newest matching records. With ``after`` it
    returns only the records written since that cursor, which is how a client tails
    the log. A cursor beyond the end of the file means the file rotated, so the
    newest records are returned instead.

    Args:
        limit: Most records to return.
        min_level: Lowest severity to include, or None for all.
        search: Case-insensitive text a record must contain, or None.
        after: Cursor from an earlier page, or None for the newest records.

    Returns:
        The matching records, oldest first, and the cursor for the next call.

    Raises:
        NotFoundError: If the viewer is disabled.
    """
    if not core_config.settings.logs_viewer_enabled:
        raise core_exceptions.NotFoundError("The log viewer is not available")
    path = Path(core_config.settings.LOGS_DIR) / LOG_FILE_NAME
    try:
        size = path.stat().st_size
    except FileNotFoundError:
        return logs_schema.LogPage(entries=[], cursor=0)

    # A cursor always sits on a line boundary; any other start may fall mid-line.
    at_line_start = after is not None and after <= size
    start = after if at_line_start else max(0, size - MAX_READ_BYTES)
    if size - start > MAX_READ_BYTES:
        start, at_line_start = size - MAX_READ_BYTES, False
    with path.open("rb") as log_file:
        log_file.seek(start)
        chunk = log_file.read(size - start)

    if start > 0 and not at_line_start:
        rest = chunk.partition(b"\n")[2]
        start += len(chunk) - len(rest)
        chunk = rest
    complete_end = chunk.rfind(b"\n") + 1
    entries = _parse_entries(chunk[:complete_end].decode("utf-8", errors="replace").splitlines())
    matching = [entry for entry in entries if _matches(entry, min_level, search)]
    return logs_schema.LogPage(entries=matching[-limit:], cursor=start + complete_end)


def clear_logs(admin_id: int) -> None:
    """Empty the log file and delete its rotated backups.

    The file is truncated in place, so the logging handler keeps its open file and
    writes on from the start. The clear is recorded as the first line of the new log.

    Args:
        admin_id: ID of the admin who cleared the logs.

    Raises:
        NotFoundError: If the viewer is disabled.
    """
    if not core_config.settings.logs_viewer_enabled:
        raise core_exceptions.NotFoundError("The log viewer is not available")
    path = Path(core_config.settings.LOGS_DIR) / LOG_FILE_NAME
    for backup in path.parent.glob(f"{LOG_FILE_NAME}.*"):
        if backup.suffix[1:].isdigit():
            backup.unlink(missing_ok=True)
    if path.is_file():
        with path.open("r+b") as log_file:
            log_file.truncate(0)
    logger.warning("Server logs cleared", extra=core_logger.context(admin_id=admin_id))


def _matches(entry: logs_schema.LogEntry, min_level: logs_schema.LogLevel | None, search: str | None) -> bool:
    """Report whether a record passes the level and text filters.

    Args:
        entry: The record to test.
        min_level: Lowest severity to include, or None.
        search: Text to look for, or None.

    Returns:
        True when the record should be shown.
    """
    if min_level is not None and _LEVEL_NUMBERS.get(entry.level, 0) < _LEVEL_NUMBERS[min_level.value]:
        return False
    if not search:
        return True
    haystack = " ".join(filter(None, (entry.message, entry.logger, entry.request_id, entry.exception))).lower()
    return search.lower() in haystack


def _parse_entries(lines: list[str]) -> list[logs_schema.LogEntry]:
    """Turn log lines into records, folding traceback lines into the record above.

    Args:
        lines: Lines of the log file.

    Returns:
        One record per log entry; a line that starts no record extends the previous
        record's exception, and is dropped when there is none.
    """
    entries: list[logs_schema.LogEntry] = []
    for line in lines:
        if not line.strip():
            continue
        entry = _parse_json_line(line) or _parse_dev_line(line)
        if entry is not None:
            entries.append(entry)
        elif entries:
            previous = entries[-1]
            previous.exception = f"{previous.exception}\n{line}" if previous.exception else line
    return entries


def _parse_json_line(line: str) -> logs_schema.LogEntry | None:
    """Parse a production-format line.

    Args:
        line: One line of the log file.

    Returns:
        The record, or None when the line is not a JSON log record.
    """
    if not line.startswith("{"):
        return None
    try:
        data = json.loads(line)
    except json.JSONDecodeError:
        return None
    if not isinstance(data, dict) or "level" not in data or "message" not in data:
        return None
    return logs_schema.LogEntry(
        timestamp=data.get("timestamp"),
        level=str(data["level"]),
        logger=data.get("logger"),
        message=str(data["message"]),
        request_id=data.get("request_id"),
        context=data.get("context"),
        exception=data.get("exception"),
    )


def _parse_dev_line(line: str) -> logs_schema.LogEntry | None:
    """Parse a development-format line.

    Args:
        line: One line of the log file.

    Returns:
        The record, or None when the line does not start a record.
    """
    match = _DEV_LINE.match(line)
    if match is None:
        return None
    return logs_schema.LogEntry(
        timestamp=match["timestamp"],
        level=match["level"],
        logger=match["logger"],
        message=match["message"],
        request_id=match["request_id"] or None,
        context=None,
        exception=None,
    )
