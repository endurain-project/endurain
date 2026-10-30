"""Structured application logging for the Endurain backend.

Standard usage — one module-level logger, driven with the stdlib ``logging`` API::

    import core.logger as core_logger

    logger = core_logger.get_logger(__name__)

    logger.debug("Parsed activity", extra=core_logger.context(activity_id=42))
    logger.error("Import failed", exc_info=err)

:func:`get_logger` returns a **child of the single configured ``main_logger``**, so
every module gets its own dotted logger name (emitted as the ``logger`` field)
while sharing one handler / formatter / level pipeline. Nothing has to be
configured at the call site, and no module needs to know how logging is wired.

Structured fields travel through the stdlib ``extra=`` keyword and are rendered as
a ``context`` object in JSON (or ``key=value`` pairs in the development format).
:func:`context` builds that mapping: it drops unset (``None``) values so optional
identifiers can be passed unconditionally, and namespaces any key that would
collide with a stdlib ``LogRecord`` attribute (which the stdlib would reject).

Operator-facing lifecycle messages can be mirrored to the console with
``extra=core_logger.context(console=True)``. In deployed environments every record
already goes to stdout, so the flag is a no-op there; in development it is what
puts the message on the terminal *in addition to* the log file. This replaces the
old approach of adding and removing a handler around each call, which mutated
shared logger state from request threads and event-bus consumer threads.

Provides:
  - get_logger / context: the public logging surface used by application code.
  - JsonFormatter: structured JSON output for production.
  - _DevFormatter: human-readable text for development.
  - RequestIdFilter: injects the current request ID into
    every log record so all logs from a single request
    can be correlated.
  - ConsoleMirrorFilter: passes only records explicitly flagged for the console.
  - WebSocketKeepaliveFilter: drops websocket PING/PONG frame lines.
  - _build_handlers: environment-aware handler factory
    (stdout JSON always in production/demo; file when
    LOGS_DIR is set, rotated when one process writes it; file
    plus console mirror in development).
  - setup_main_logger: configures the main, Alembic, and
    APScheduler loggers.
"""

import json
import logging
import logging.handlers
import sys
from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any

# NOTE: ``core.config`` is intentionally NOT imported at module top level.
# ``core.config`` depends on this module to emit warnings from its settings
# validators (e.g. invalid SMTP_SECURE_TYPE, memory-backed rate limiting in
# production). A top-level import here would create a circular import that
# only fails when the entry point imports ``core.logger`` before
# ``core.config`` -- the partially-initialized ``core.logger`` module would
# not yet expose ``print_to_log_and_console`` when a validator calls it.
# ``logger`` is the lower-level module: it must not depend on ``config`` at
# import time. The two functions below that genuinely need ``settings``
# import it locally, after both modules have finished initializing.
import core.environment as core_environment
import core.middleware_request_id as core_middleware_request_id

# The single configured application logger. Every logger handed out by
# :func:`get_logger` is a child of it, so they inherit its level and handlers.
ROOT_LOGGER_NAME = "main_logger"

# Extra field flagging a record for console mirroring (see module docstring).
CONSOLE_FIELD = "console"

# Prefix applied to a caller-supplied field whose name would collide with a
# stdlib LogRecord attribute. Renaming keeps the value instead of dropping it,
# and avoids the "Attempt to overwrite %r in LogRecord" the stdlib would raise.
_RESERVED_FIELD_PREFIX = "ctx_"

# String log levels accepted by config and by the legacy helpers. ``trace`` maps
# to DEBUG because Python has no TRACE level.
_LEVELS: dict[str, int] = {
    "critical": logging.CRITICAL,
    "error": logging.ERROR,
    "warning": logging.WARNING,
    "info": logging.INFO,
    "debug": logging.DEBUG,
    "trace": logging.DEBUG,
}

# Size at which a single-writer ``app.log`` rolls over, and how many rolled files are kept.
LOG_FILE_MAX_BYTES = 10 * 1024 * 1024
LOG_FILE_BACKUP_COUNT = 5

# Format used by the development console mirror — matches uvicorn's own output
# so operator-facing lifecycle lines blend into the server log.
_CONSOLE_FORMAT = "%(levelname)s:     %(message)s"


class RequestIdFilter(logging.Filter):
    """
    Inject the current request ID into every log record.

    Reads the value from
    :func:`core_middleware_request_id.get_request_id`
    and stores it as ``record.request_id`` so formatters
    can reference ``%(request_id)s``.
    """

    def filter(self, record: logging.LogRecord) -> bool:
        """
        Add ``request_id`` attribute to the log record.

        Args:
            record: The log record to augment.

        Returns:
            Always True so the record is never suppressed.
        """
        record.request_id = (  # type: ignore[attr-defined]
            core_middleware_request_id.get_request_id()
        )
        return True


class ConsoleMirrorFilter(logging.Filter):
    """
    Pass only records explicitly flagged for console mirroring.

    Attached to the development console handler so a record reaches the terminal
    exactly when the caller opted in with ``extra=context(console=True)``.
    Everything else goes to the log file only. This preserves the previous
    behaviour of ``print_to_log_and_console`` without mutating shared handler
    state on every call, which was unsafe across request and consumer threads.
    """

    def filter(self, record: logging.LogRecord) -> bool:
        """
        Report whether the record opted into console output.

        Args:
            record: The log record to test.

        Returns:
            True when the record carries a truthy ``console`` field.
        """
        return bool(getattr(record, CONSOLE_FIELD, False))


class WebSocketKeepaliveFilter(logging.Filter):
    """
    Drop the PING/PONG keepalive frames the websockets library logs at DEBUG.

    Uvicorn hands its ``uvicorn.error`` logger to the websockets protocol, so every
    keepalive frame is logged beside Uvicorn's other debug output and cannot be
    silenced by logger name or level alone.
    """

    _PREFIXES = ("> PING", "< PING", "> PONG", "< PONG")

    def filter(self, record: logging.LogRecord) -> bool:
        """
        Report whether the record is something other than a keepalive frame.

        Args:
            record: The log record to test.

        Returns:
            False for a PING/PONG frame line, True otherwise.
        """
        return not record.getMessage().startswith(self._PREFIXES)


# Shared instance so repeated ``setup_main_logger`` calls attach it once.
_WEBSOCKET_KEEPALIVE_FILTER = WebSocketKeepaliveFilter()


# Attributes always present on a LogRecord — excluded from the extra
# context dict so we only surface caller-supplied fields.
_STDLIB_RECORD_ATTRS: frozenset[str] = frozenset(
    (
        "name",
        "msg",
        "args",
        "levelname",
        "levelno",
        "pathname",
        "filename",
        "module",
        "exc_info",
        "exc_text",
        "stack_info",
        "lineno",
        "funcName",
        "created",
        "msecs",
        "relativeCreated",
        "thread",
        "threadName",
        "processName",
        "process",
        "message",
        "taskName",
        "request_id",
        "asctime",
    )
)

# Record attributes that are never rendered as structured context: the stdlib
# ones above plus our own routing flag, which is plumbing rather than data.
_NON_CONTEXT_ATTRS: frozenset[str] = _STDLIB_RECORD_ATTRS | {CONSOLE_FIELD}


def _record_context(record: logging.LogRecord) -> dict[str, Any]:
    """
    Extract the caller-supplied structured fields from a record.

    Args:
        record: The log record to inspect.

    Returns:
        The fields passed via ``extra=``, without stdlib attributes or the
        console-routing flag.
    """
    return {k: v for k, v in record.__dict__.items() if k not in _NON_CONTEXT_ATTRS}


def get_logger(name: str | None = None) -> logging.Logger:
    """
    Return the module logger to use for application logging.

    The returned logger is a child of the single configured ``main_logger``, so
    it inherits that logger's level and handlers while keeping its own name.
    Call it once per module with ``__name__``::

        logger = core_logger.get_logger(__name__)

    Args:
        name: Dotted module name, normally ``__name__``. When omitted (or when
            it is already the root name) the root application logger is
            returned.

    Returns:
        The configured :class:`logging.Logger` for that name.
    """
    if not name or name == ROOT_LOGGER_NAME:
        return logging.getLogger(ROOT_LOGGER_NAME)
    if name.startswith(f"{ROOT_LOGGER_NAME}."):
        return logging.getLogger(name)
    return logging.getLogger(f"{ROOT_LOGGER_NAME}.{name}")


def _normalize_fields(fields: Mapping[str, Any]) -> dict[str, Any]:
    """
    Build a safe ``extra`` mapping from caller-supplied fields.

    Drops ``None`` values so optional identifiers can be passed unconditionally,
    and prefixes any key that collides with a stdlib ``LogRecord`` attribute
    (which the stdlib would otherwise reject outright). The console-routing flag
    is passed through untouched — it is ours, not the stdlib's.

    Args:
        fields: The caller's structured fields.

    Returns:
        A mapping safe to pass as ``extra=``.
    """
    normalized: dict[str, Any] = {}
    for key, value in fields.items():
        if value is None:
            continue
        safe_key = f"{_RESERVED_FIELD_PREFIX}{key}" if key in _STDLIB_RECORD_ATTRS else key
        normalized[safe_key] = value
    return normalized


def context(*, console: bool = False, **fields: Any) -> dict[str, Any]:
    """
    Build the ``extra`` mapping for a structured log record.

    Usage::

        logger.info(
            "Stored activity",
            extra=core_logger.context(activity_id=activity.id, user_id=user_id),
        )

    Args:
        console: Mirror this record to the console as well as the log file.
            No-op in deployed environments, where every record already reaches
            stdout.
        **fields: Structured fields to attach. ``None`` values are dropped.

    Returns:
        A mapping to pass as the ``extra=`` argument of a logging call.
    """
    extra = _normalize_fields(fields)
    if console:
        extra[CONSOLE_FIELD] = True
    return extra


class JsonFormatter(logging.Formatter):
    """
    Format log records as newline-delimited JSON.

    Suitable for collection by container orchestrators
    (Docker, Kubernetes) and log aggregation pipelines.
    Each record becomes one JSON object on a single line.
    Any extra fields supplied via ``extra={}`` are emitted
    under a ``context`` key.
    """

    def format(self, record: logging.LogRecord) -> str:
        """
        Serialise a log record to a JSON string.

        Args:
            record: The log record to format.

        Returns:
            Single-line JSON string representing the record.
        """
        entry: dict = {
            "timestamp": datetime.fromtimestamp(record.created, tz=UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        rid = getattr(record, "request_id", "")
        if rid:
            entry["request_id"] = rid
        if record.exc_info:
            entry["exception"] = self.formatException(record.exc_info)
        record_context = _record_context(record)
        if record_context:
            entry["context"] = record_context
        return json.dumps(entry, default=str)


class _DevFormatter(logging.Formatter):
    """
    Human-readable formatter for the development log file and console mirror.

    Appends any caller-supplied ``extra`` fields as a
    space-separated ``key=value`` string after the message
    so engineers can see structured context at a glance.
    """

    _BASE = "%(asctime)s - %(name)s - %(levelname)s - [%(request_id)s] - %(message)s"

    def __init__(self, fmt: str = _BASE) -> None:
        """
        Build the formatter.

        Args:
            fmt: The format of the line the context is appended to.
        """
        super().__init__(fmt)

    def format(self, record: logging.LogRecord) -> str:
        """
        Format the record with extra context appended.

        Args:
            record: The log record to format.

        Returns:
            Formatted string with optional context suffix.
        """
        base = super().format(record)
        record_context = _record_context(record)
        if not record_context:
            return base
        ctx_str = " ".join(f"{k}={v!r}" for k, v in record_context.items())
        return f"{base} | {ctx_str}"


def _build_handlers(log_level: int) -> list[logging.Handler]:
    """
    Build the appropriate log handlers for the environment.

    Production always emits JSON to stdout so container
    orchestrators can collect structured logs without file
    mounts. If ``LOGS_DIR`` is configured, a ``FileHandler``
    writing JSON to ``{LOGS_DIR}/app.log`` is also added so
    Docker volume mounts continue to receive log output.
    Development writes human-readable text to
    ``{LOGS_DIR}/app.log`` plus a console mirror that only
    emits records flagged with ``context(console=True)``.

    Args:
        log_level: Python logging level constant.

    Returns:
        List of configured :class:`logging.Handler` instances.
    """
    # Local import: see top-of-module note. ``setup_main_logger`` /
    # ``_build_handlers`` run at app startup, never at import time, so by the
    # time we get here ``core.config`` is fully initialized.
    import core.config as core_config

    def _file_handler(path: str) -> logging.FileHandler:
        # Rotation renames the file under the other writers, so it is only safe
        # when this is the sole process writing it.
        if core_config.settings.single_log_writer:
            return logging.handlers.RotatingFileHandler(
                path, maxBytes=LOG_FILE_MAX_BYTES, backupCount=LOG_FILE_BACKUP_COUNT
            )
        return logging.FileHandler(path)

    def _configure(handler: logging.Handler, formatter: logging.Formatter) -> logging.Handler:
        handler.setFormatter(formatter)
        handler.setLevel(log_level)
        handler.addFilter(RequestIdFilter())
        return handler

    # Treat both "production" and "demo" as deployed
    # environments where stdout JSON is preferred.
    is_deployed = core_environment.is_deployed_environment(core_config.settings.ENVIRONMENT)
    if is_deployed:
        handlers: list[logging.Handler] = [_configure(logging.StreamHandler(sys.stdout), JsonFormatter())]
        # Also write to file when LOGS_DIR is configured so that Docker
        # volume mounts (e.g. /app/backend/logs) continue to receive log
        # output regardless of the ENVIRONMENT value.
        if core_config.settings.LOGS_DIR:
            log_path = f"{core_config.settings.LOGS_DIR}/app.log"
            handlers.append(_configure(_file_handler(log_path), JsonFormatter()))
        # No console mirror here: stdout already carries every record, so adding
        # one would duplicate every operator-facing line.
        return handlers

    log_path = f"{core_config.settings.LOGS_DIR}/app.log"
    console_mirror = _configure(logging.StreamHandler(sys.stdout), _DevFormatter(_CONSOLE_FORMAT))
    console_mirror.addFilter(ConsoleMirrorFilter())
    return [
        _configure(_file_handler(log_path), _DevFormatter()),
        console_mirror,
    ]


def _replace_handlers(
    loggers: tuple[logging.Logger, ...],
    handlers: list[logging.Handler],
) -> None:
    """
    Replace handlers on a set of related loggers.

    Args:
        loggers: Loggers that should share the given handlers.
        handlers: Handlers to attach to every logger.

    Returns:
        None.

    Raises:
        None.
    """
    old_handlers: set[logging.Handler] = set()
    for logger in loggers:
        old_handlers.update(logger.handlers)
        for old_handler in list(logger.handlers):
            logger.removeHandler(old_handler)
        for handler in handlers:
            logger.addHandler(handler)
        logger.propagate = False

    for old_handler in old_handlers:
        old_handler.close()


class _SlowapiLimitExceededFilter(logging.Filter):
    """Drop slowapi's own "limit exceeded" record, which the 429 handler already logs with the route."""

    def filter(self, record: logging.LogRecord) -> bool:
        """Keep every record except slowapi's per-request limit-exceeded line.

        Args:
            record: The record being logged.

        Returns:
            False for the limit-exceeded line, True otherwise.
        """
        return not str(record.msg).startswith("ratelimit ")


def setup_main_logger():
    """
    Set up the main application logger.

    Selects handlers appropriate for the current
    environment (JSON stdout in production, plain-text
    file plus console mirror in development). Attaches the
    same handlers to the Alembic and APScheduler loggers so
    their output is captured consistently.

    Returns:
        logging.Logger: The configured main logger instance.
    """
    # Local import: see top-of-module note. Deferring this keeps
    # ``core.logger`` free of any import-time dependency on ``core.config``.
    import core.config as core_config

    # Get log level from config, default to WARNING if invalid
    log_level = _LEVELS.get(
        core_config.settings.LOG_LEVEL.lower(),
        logging.WARNING,
    )

    main_logger = logging.getLogger(ROOT_LOGGER_NAME)
    alembic_logger = logging.getLogger("alembic")
    scheduler_logger = logging.getLogger("apscheduler")
    # Structured upload-audit events emitted by safeuploads.
    # Attaching it here ensures correlation IDs and validation
    # outcomes flow through the same handler/format pipeline
    # as the rest of the backend logs.
    safeuploads_audit_logger = logging.getLogger("safeuploads.audit")
    # slowapi reports a rate-limit storage outage and its recovery here; without handlers they would
    # reach stderr unstructured, and its own handler discards them.
    slowapi_logger = logging.getLogger("slowapi")
    if not any(isinstance(f, _SlowapiLimitExceededFilter) for f in slowapi_logger.filters):
        slowapi_logger.addFilter(_SlowapiLimitExceededFilter())

    for logger in (
        main_logger,
        alembic_logger,
        scheduler_logger,
        safeuploads_audit_logger,
        slowapi_logger,
    ):
        logger.setLevel(log_level)

    handlers = _build_handlers(log_level)
    _replace_handlers(
        (
            main_logger,
            alembic_logger,
            scheduler_logger,
            safeuploads_audit_logger,
            slowapi_logger,
        ),
        handlers,
    )
    safeuploads_audit_logger.propagate = True

    uvicorn_logger = logging.getLogger("uvicorn.error")
    if core_config.settings.LOG_WEBSOCKET_FRAMES:
        uvicorn_logger.removeFilter(_WEBSOCKET_KEEPALIVE_FILTER)
    else:
        uvicorn_logger.addFilter(_WEBSOCKET_KEEPALIVE_FILTER)

    return main_logger
