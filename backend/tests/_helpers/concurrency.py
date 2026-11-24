"""Helpers for tests where one database session must wait for another's lock."""

import threading
import time
from collections.abc import Callable
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session, sessionmaker


def wait_until_a_session_waits_for_a_lock(factory: sessionmaker[Session], timeout: float = 10.0) -> None:
    """Block until another session of this database waits on a lock, so a test acts at that exact point.

    Args:
        factory: The session factory of the test database.
        timeout: Seconds to wait before failing.

    Raises:
        AssertionError: If no session waited for a lock in time.
    """
    deadline = time.monotonic() + timeout
    with factory() as probe:
        while time.monotonic() < deadline:
            waiting = probe.scalar(
                text(
                    "SELECT count(*) FROM pg_stat_activity "
                    "WHERE datname = current_database() AND wait_event_type = 'Lock' AND pid <> pg_backend_pid()"
                )
            )
            if waiting:
                return
            # PostgreSQL reads pg_stat_activity once per transaction, so each poll needs a transaction of its own.
            probe.rollback()
            threading.Event().wait(0.02)
    raise AssertionError("no session waited for a lock")


class Worker:
    """Runs a function on a thread of its own and keeps what it returned or raised."""

    def __init__(self, work: Callable[[], Any]) -> None:
        self.result: Any = None
        self.error: BaseException | None = None
        self._thread = threading.Thread(target=self._run, args=(work,))
        self._thread.start()

    def _run(self, work: Callable[[], Any]) -> None:
        try:
            self.result = work()
        except BaseException as err:
            self.error = err

    @property
    def done(self) -> bool:
        """Whether the function has finished."""
        return not self._thread.is_alive()

    def join(self) -> None:
        """Wait for the function to finish, failing when it does not."""
        self._thread.join(timeout=20)
        assert not self._thread.is_alive(), "the worker did not finish: a lock was never released"
