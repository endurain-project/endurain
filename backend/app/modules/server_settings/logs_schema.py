"""Pydantic shapes for the admin server-log viewer."""

from enum import StrEnum

from pydantic import BaseModel, Field, StrictBool, StrictInt, StrictStr


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


class LogPage(BaseModel):
    """A slice of the application log.

    Attributes:
        entries: Matching records, oldest first.
        cursor: Position to pass as ``after`` to receive only records written after this slice.
    """

    entries: list[LogEntry]
    cursor: StrictInt = Field(..., ge=0, description="Pass as `after` to read only newer records")
