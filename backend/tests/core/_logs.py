"""Capture what a module's own logger writes, without replacing the logger."""

import contextlib
import logging
from collections.abc import Iterator


class Captured:
    """The records a logger wrote while it was captured."""

    def __init__(self) -> None:
        self.records: list[logging.LogRecord] = []

    @property
    def messages(self) -> list[str]:
        """Every message, in the order it was written."""
        return [record.getMessage() for record in self.records]

    @property
    def warnings(self) -> list[str]:
        """The messages written at WARNING."""
        return [r.getMessage() for r in self.records if r.levelno == logging.WARNING]

    @property
    def text(self) -> str:
        """Every message, joined."""
        return " ".join(self.messages)

    @property
    def warning_text(self) -> str:
        """The warning messages, joined."""
        return " ".join(self.warnings)


class _Collector(logging.Handler):
    def __init__(self, sink: list[logging.LogRecord]) -> None:
        super().__init__(logging.DEBUG)
        self._sink = sink

    def emit(self, record: logging.LogRecord) -> None:
        self._sink.append(record)


@contextlib.contextmanager
def capture(logger: logging.Logger) -> Iterator[Captured]:
    """Collect everything ``logger`` writes inside the block, at every level.

    Args:
        logger: The logger to capture.

    Yields:
        The records, filling as the block runs.
    """
    captured = Captured()
    handler = _Collector(captured.records)
    level = logger.level
    logger.addHandler(handler)
    logger.setLevel(logging.DEBUG)
    try:
        yield captured
    finally:
        logger.setLevel(level)
        logger.removeHandler(handler)
