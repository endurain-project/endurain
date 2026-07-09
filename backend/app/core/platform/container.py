"""The composition root: build the platform substrate from settings.

``build_platform`` resolves each capability (state, storage, events, lock,
clock) to a concrete backend based on the deployment profile and returns a
frozen ``Platform`` holding the five providers. It is called once at startup and
attached to ``app.state.platform``; the FastAPI dependencies in
``core.platform.deps`` expose the providers to routes and handlers.

Every capability resolves its backend by URI scheme, independently of the
profile: ``memory``/``redis`` for ``STATE_URI``; ``local``/``s3`` for
``STORAGE_URI``; ``memory``/``redis`` for ``EVENTS_URI``; ``noop``/
``postgres-advisory`` for ``LOCK_URI``. The deployment profile only shapes the
*defaults* those URIs resolve to (see ``core.config`` ``resolved_*`` properties),
so ``local``, ``distributed``, and ``custom`` all build the same way — the
profile just picks memory-vs-Redis and local-fs-vs-S3 defaults.
"""

from dataclasses import dataclass
from typing import TYPE_CHECKING

from core.platform.backends.clock_system import SystemClock
from core.platform.backends.events_inprocess import InProcessEventBus
from core.platform.backends.events_redis import RedisStreamEventBus
from core.platform.backends.lock_noop import NoopLock
from core.platform.backends.lock_pg import PgAdvisoryLock
from core.platform.backends.state_memory import MemoryState
from core.platform.backends.state_redis import RedisState
from core.platform.backends.storage_local import LocalStorage
from core.platform.profile import DeploymentProfile
from core.platform.providers import (
    ClockProvider,
    EventBusProvider,
    EventRecorder,
    LockProvider,
    StateProvider,
    StorageProvider,
)

if TYPE_CHECKING:
    from core.config import Settings


@dataclass(frozen=True)
class Platform:
    """The assembled platform substrate — one instance per process.

    Attributes:
        profile: The active deployment profile.
        state: Ephemeral keyed-state provider.
        storage: Blob-storage provider.
        events: Publish/subscribe provider.
        lock: Coordination-lock provider.
        clock: Time-source provider.
    """

    profile: DeploymentProfile
    state: StateProvider
    storage: StorageProvider
    events: EventBusProvider
    lock: LockProvider
    clock: ClockProvider


def build_platform(settings: "Settings") -> Platform:
    """Assemble the ``Platform`` for the configured deployment profile.

    Args:
        settings: The application settings (deployment profile + capability config).

    Returns:
        A frozen ``Platform`` wiring each provider to its selected backend.

    Raises:
        ValueError: When a capability URI uses an unsupported scheme.
        RuntimeError: When a selected Redis backend cannot be reached.
    """
    profile = settings.DEPLOYMENT_PROFILE
    return Platform(
        profile=profile,
        state=_build_state(settings),
        storage=_build_storage(settings),
        events=_build_events(settings),
        lock=_build_lock(settings),
        clock=SystemClock(),
    )


def _build_state(settings: "Settings") -> StateProvider:
    state_uri = settings.resolved_state_uri
    scheme, _, _ = state_uri.partition("://")
    if scheme == "memory":
        return MemoryState()
    if scheme in ("redis", "rediss", "unix"):
        return RedisState.from_uri(state_uri)
    raise ValueError(f"Unsupported STATE_URI scheme: {scheme or state_uri!r}")


def _build_storage(settings: "Settings") -> StorageProvider:
    storage_uri = settings.resolved_storage_uri
    scheme, _, rest = storage_uri.partition("://")
    if scheme == "local":
        # Root the backend at DATA_DIR; each storage *area* (thumbnails, media,
        # user images, ...) is a subdirectory under it.
        return LocalStorage(rest or settings.DATA_DIR)
    if scheme == "s3":
        # Imported lazily: boto3 is the optional `s3` extra and is absent from the
        # default image, so a top-level import would break non-S3 deployments.
        from core.platform.backends.storage_s3 import S3Storage

        return S3Storage.from_uri(storage_uri)
    raise ValueError(f"Unsupported STORAGE_URI scheme: {scheme or storage_uri!r}")


def _build_events(settings: "Settings") -> EventBusProvider:
    events_uri = settings.resolved_events_uri
    scheme, _, _ = events_uri.partition("://")
    recorder = _build_event_recorder(settings)
    if scheme == "memory":
        return InProcessEventBus(recorder=recorder)
    if scheme in ("redis", "rediss", "unix"):
        return RedisStreamEventBus.from_uri(events_uri, recorder=recorder)
    raise ValueError(f"Unsupported EVENTS_URI scheme: {scheme or events_uri!r}")


def _build_event_recorder(settings: "Settings") -> EventRecorder | None:
    if not settings.EVENT_LOG_ENABLED:
        return None
    # Imported lazily: the recorder pulls in the ORM/session layer, which the
    # pure providers/events modules deliberately do not depend on.
    from core.event_log.recorder import EventLogRecorder

    return EventLogRecorder()


def _build_lock(settings: "Settings") -> LockProvider:
    lock_uri = settings.resolved_lock_uri
    scheme, _, _ = lock_uri.partition("://")
    if scheme == "noop":
        return NoopLock()
    if scheme == "postgres-advisory":
        return PgAdvisoryLock.from_main_database()
    raise ValueError(f"Unsupported LOCK_URI scheme: {scheme or lock_uri!r}")
