"""The clock a test drives, and the in-memory state that expires keys by it."""

import jasil.runtime as jasil_runtime
from jasil.backends.state_memory import MemoryState
from jasil.testing import FixedClock


def platform_clock() -> FixedClock:
    """Return the clock of the active test platform; advancing it moves every backend the platform built."""
    clock = jasil_runtime.get_active_platform().clock
    assert isinstance(clock, FixedClock)
    return clock


def memory_state() -> MemoryState:
    """Return a fresh in-memory state that expires keys by the active platform's clock."""
    return MemoryState(platform_clock())
