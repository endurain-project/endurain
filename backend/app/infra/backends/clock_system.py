"""System ``ClockProvider`` backend."""

import time
from datetime import UTC, datetime


class SystemClock:
    """``ClockProvider`` backed by the system clock (UTC wall time + monotonic)."""

    def now(self) -> datetime:
        return datetime.now(UTC)

    def monotonic(self) -> float:
        return time.monotonic()
