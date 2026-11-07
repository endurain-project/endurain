"""Pydantic shapes for the admin server-log viewer."""

from enum import StrEnum

from pydantic import BaseModel, StrictBool, StrictStr

import core.pagination as core_pagination


class LogLevel(StrEnum):
    """Log levels an admin can filter by, from least to most severe."""

    DEBUG = "DEBUG"
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"


class LogsStatus(BaseModel):
    """Whether the log viewer is available on this deployment.

    Attributes:
        enabled: True when the application log can be read through the API.
    """

    enabled: StrictBool


class LogEntry(BaseModel):
    """One record of the application log.

    Attributes:
        timestamp: When the record was written, as the log wrote it, or null if unknown.
        level: Severity of the record.
        logger: Dotted name of the logger that emitted it, or null if unknown.
        message: The log message.
        request_id: ID of the HTTP request that produced it, or null.
        context: Structured fields attached to the record, or null.
        exception: Formatted traceback, or null.
    """

    timestamp: StrictStr | None
    level: StrictStr
    logger: StrictStr | None
    message: StrictStr
    request_id: StrictStr | None
    context: dict[str, object] | None
    exception: StrictStr | None


#: A slice of the application log: ``items`` are the matching records, oldest first, and ``next_cursor`` is the
#: position to pass as ``cursor`` to receive only records written after this slice. It is always set, because the
#: log keeps growing at its end.
LogPage = core_pagination.CursorPage[LogEntry]
