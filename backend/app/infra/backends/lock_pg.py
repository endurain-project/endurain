"""PostgreSQL advisory-lock ``LockProvider`` backend.

Only imported by the composition root when ``LOCK_URI`` selects
``postgres-advisory://`` (the distributed-profile default), so single-process
deployments never load it. ``try_acquire`` is non-blocking
(``pg_try_advisory_lock``) and holds one dedicated connection open for the
lock's lifetime, releasing it with ``pg_advisory_unlock`` on exit — so at most
one replica runs a coordinated job (e.g. the thumbnail backfill) at a time.

The lock lives on the main database, so no extra infrastructure is required; the
lock name is hashed to a signed 64-bit key because ``pg_advisory_lock`` keys are
``bigint``.
"""

import hashlib
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

from sqlalchemy import text

import core.database as core_database
import core.logger as core_logger

logger = core_logger.get_logger(__name__)


def advisory_key(name: str) -> int:
    """Map a lock name to a signed 64-bit key for ``pg_advisory_lock``.

    Args:
        name: The logical lock name (e.g. ``thumbnail_backfill``).

    Returns:
        A deterministic signed 64-bit integer, so every replica derives the same
        key from the same name and contends for the same lock.
    """
    return int.from_bytes(hashlib.sha256(name.encode()).digest()[:8], "big", signed=True)


class PgAdvisoryLock:
    """``LockProvider`` using PostgreSQL session-level advisory locks on the main DB.

    ``try_acquire`` is non-blocking; it holds one connection open while the lock
    is held and releases it on exit. ``ttl_seconds`` does not apply — a session
    advisory lock lives until it is unlocked or the connection is dropped.
    """

    def __init__(self, engine: Any) -> None:
        self._engine = engine

    @classmethod
    def from_main_database(cls) -> "PgAdvisoryLock":
        """Build against the application's main SQLAlchemy engine."""
        return cls(core_database.engine)

    @contextmanager
    def try_acquire(self, name: str, ttl_seconds: int | None = None) -> Iterator[bool]:
        del ttl_seconds  # session advisory locks are not TTL-based
        key = advisory_key(name)
        connection = self._engine.connect()
        acquired = False
        try:
            result = connection.execute(text("SELECT pg_try_advisory_lock(CAST(:key AS bigint))"), {"key": key})
            acquired = bool(result.scalar())
            yield acquired
        finally:
            if acquired:
                try:
                    connection.execute(text("SELECT pg_advisory_unlock(CAST(:key AS bigint))"), {"key": key})
                except Exception as error:
                    # Never let an unlock failure mask a body exception; drop the
                    # still-locked connection so its backend session (and the
                    # lock) is discarded instead of returned to the pool.
                    logger.error(f"Failed to release advisory lock {name!r}", exc_info=error)
                    connection.invalidate()
            connection.close()
