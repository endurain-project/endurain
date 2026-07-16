"""Platform providers — the tiny interfaces domain code depends on.

Pure module: only stdlib typing and the event envelope. No infrastructure
(redis / boto3 / sqlalchemy) and no domain imports, so any module can depend on
these providers without pulling in a backend. Concrete backends live in
``infra.backends`` and are selected by the composition root
(``infra.container.build_platform``).
"""

from collections.abc import Callable, Iterator
from contextlib import AbstractContextManager
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol, runtime_checkable

from infra.events import Event


class StateBackendUnavailableError(RuntimeError):
    """Raised by a :class:`StateProvider` when its backing store is unreachable.

    Lets domain stores react to an infrastructure outage (e.g. surface a 503 or
    swallow a best-effort cleanup) without knowing or importing anything about
    the concrete backend (Redis). The in-memory backend never raises it.
    """


@dataclass(frozen=True)
class TieredFailureOutcome:
    """Result of an atomic tiered-lockout increment.

    Attributes:
        count: The failure counter value after this attempt.
        locked_until_epoch: Wall-clock epoch (seconds) the lock is active until,
            or ``None`` when not locked.
        newly_locked: True only when *this* call created (or renewed) the lock.
    """

    count: int
    locked_until_epoch: int | None
    newly_locked: bool


@runtime_checkable
class StateProvider(Protocol):
    """Ephemeral keyed state (counters, TTL flags, small blobs).

    The single seam through which domain code reads and writes short-lived
    shared state, so a store never needs to know whether it is backed by a
    process-local dict (``local``) or Redis (``distributed``). Beyond plain
    key/value access it exposes the few *atomic* primitives the auth/MFA/ticket
    stores need (``set_if_absent``, ``get_and_delete``, ``record_tiered_failure``)
    so their correctness does not depend on the backend.
    """

    def get(self, key: str) -> bytes | None: ...
    def set(self, key: str, value: bytes, ttl_seconds: int | None = None) -> None: ...
    def set_if_absent(self, key: str, value: bytes, ttl_seconds: int | None = None) -> bool: ...
    def get_and_delete(self, key: str) -> bytes | None: ...
    def delete(self, key: str) -> None: ...
    def delete_prefix(self, prefix: str) -> int: ...
    def iter_keys(self, prefix: str) -> Iterator[str]: ...
    def incr(self, key: str, amount: int = 1, ttl_seconds: int | None = None) -> int: ...
    def record_tiered_failure(
        self,
        counter_key: str,
        gate_key: str,
        tiers: tuple[tuple[int, int], ...],
        counter_ttl_seconds: int,
    ) -> TieredFailureOutcome: ...


@runtime_checkable
class StorageProvider(Protocol):
    """Opaque byte-blob storage addressed by a key within a named *area*.

    An area is a domain-owned namespace (e.g. ``"activity_thumbnails"``,
    ``"user_images"``) so one backend serves every subsystem: locally it maps to
    a subdirectory, on S3 to a key prefix. The DB stores only the key (the area
    is a fixed constant of the calling domain); ``url`` is computed at
    serialization time so migrating local -> S3 needs no data migration.
    """

    def save(self, area: str, key: str, data: bytes, content_type: str | None = None) -> str: ...
    def exists(self, area: str, key: str) -> bool: ...
    def delete(self, area: str, key: str) -> None: ...
    def url(self, area: str, key: str, expires_in: int = 3600) -> str: ...


@runtime_checkable
class EventBusProvider(Protocol):
    """Publish/subscribe — synchronous in-process, or durable via Redis Streams."""

    def publish(self, event: Event) -> None: ...
    def subscribe(self, event_type: str, handler: Callable[[Event], None]) -> None: ...
    def start(self) -> None: ...
    def stop(self) -> None: ...


@runtime_checkable
class EventRecorder(Protocol):
    """Records each event's lifecycle to durable storage for observability.

    Injected into the event bus by the composition root when event logging is
    enabled. Recording must never disrupt event processing, so implementations
    swallow and log their own storage errors. :meth:`record_published` and
    :meth:`record_queued` insert the initial row for a bus-delivered or
    durable-delivered event respectively. :meth:`track` wraps handler
    execution — it marks the event *processing* on entry (unless
    ``record_processing`` is False, for a synchronous single-process dispatch
    where the intermediate state is never observed) and *completed* / *failed* on
    exit, re-raising any handler exception so the bus keeps its own error
    semantics (propagate in-process, leave pending on Redis Streams).
    """

    def record_published(self, event: Event) -> None: ...
    def record_queued(self, event: Event) -> None: ...
    def track(
        self,
        event: Event,
        *,
        worker_id: str,
        handler_name: str | None,
        record_processing: bool = True,
    ) -> AbstractContextManager[None]: ...


@runtime_checkable
class LockProvider(Protocol):
    """Best-effort mutual exclusion for scheduled/backfill work."""

    def try_acquire(self, name: str, ttl_seconds: int | None = None) -> AbstractContextManager[bool]: ...


@runtime_checkable
class ClockProvider(Protocol):
    """Injectable time source for testability."""

    def now(self) -> datetime: ...
    def monotonic(self) -> float: ...
