"""The composition root: build the platform substrate from settings.

``build_platform`` resolves each capability (state, storage, events, lock,
clock) to a concrete backend based on the deployment profile and returns a
frozen ``Platform`` holding the providers. It is called once at startup and
attached to ``app.state.platform`` and published process-wide via
``infra.runtime`` so both request and non-request code resolve the same
instance.

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

import core.config as core_config
import core.logger as core_logger
from infra.backends.clock_system import SystemClock
from infra.backends.events_inprocess import InProcessEventBus
from infra.backends.events_redis import RedisStreamEventBus
from infra.backends.geocoding_http import HttpGeocoding, NullGeocoding, build_reverse_endpoint
from infra.backends.lock_noop import NoopLock
from infra.backends.lock_pg import PgAdvisoryLock
from infra.backends.state_memory import MemoryState
from infra.backends.state_redis import RedisState
from infra.backends.storage_local import LocalStorage
from infra.profile import DeploymentProfile
from infra.providers import (
    ClockProvider,
    EventBusProvider,
    EventRecorder,
    GeocodingProvider,
    LockProvider,
    StateProvider,
    StorageProvider,
)

if TYPE_CHECKING:
    from core.config import Settings

logger = core_logger.get_logger(__name__)

#: Reverse-geocoding services this build knows how to talk to.
_GEOCODING_SERVICES = ("nominatim", "photon", "geocode")


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
        geocoding: Reverse-geocoding provider. Always present — when geocoding is
            unconfigured or misconfigured this is a no-op backend, so callers
            never branch on whether the capability exists.
        recorder: Event-log recorder, or ``None`` when event logging is disabled.
            Shared by the event bus (best-effort delivery) and the publish facade
            (durable delivery) so both paths land in the event_log dashboard.
    """

    profile: DeploymentProfile
    state: StateProvider
    storage: StorageProvider
    events: EventBusProvider
    lock: LockProvider
    clock: ClockProvider
    geocoding: GeocodingProvider
    recorder: EventRecorder | None


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
    # Build the recorder once and share it: the event bus records the lifecycle
    # of best-effort (bus-delivered) events, while the publish facade uses the
    # same recorder to record 'published' for durable (outbox-delivered) events
    # so the event_log dashboard never goes dark when durable jobs are enabled.
    recorder = _build_event_recorder(settings)
    return Platform(
        profile=profile,
        state=_build_state(settings),
        storage=_build_storage(settings),
        events=_build_events(settings, recorder),
        lock=_build_lock(settings),
        clock=SystemClock(),
        geocoding=_build_geocoding(settings),
        recorder=recorder,
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
        from infra.backends.storage_s3 import S3Storage

        return S3Storage.from_uri(storage_uri)
    raise ValueError(f"Unsupported STORAGE_URI scheme: {scheme or storage_uri!r}")


def _build_events(settings: "Settings", recorder: EventRecorder | None) -> EventBusProvider:
    events_uri = settings.resolved_events_uri
    scheme, _, _ = events_uri.partition("://")
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
    from infra.event_log.recorder import EventLogRecorder

    return EventLogRecorder()


def _build_lock(settings: "Settings") -> LockProvider:
    lock_uri = settings.resolved_lock_uri
    scheme, _, _ = lock_uri.partition("://")
    if scheme == "noop":
        return NoopLock()
    if scheme == "postgres-advisory":
        return PgAdvisoryLock.from_main_database()
    raise ValueError(f"Unsupported LOCK_URI scheme: {scheme or lock_uri!r}")


def _build_geocoding(settings: "Settings") -> GeocodingProvider:
    """Resolve the reverse-geocoding backend, falling back to a no-op.

    Unlike the other capabilities this never raises on a bad configuration:
    geocoding is optional enrichment, so an unsupported provider, an unset API
    key, or a host that fails SSRF validation disables the capability rather than
    preventing the application from starting.

    Because a disabled capability is otherwise invisible — activities simply have
    no city/town/country and nothing says why — every outcome is logged at
    startup, including the successful one. An operator who set the config and saw
    no locations appear can tell from one line whether the setting was rejected
    and for what reason.

    Args:
        settings: The application settings.

    Returns:
        The configured :class:`HttpGeocoding`, or :class:`NullGeocoding` when
        geocoding is unconfigured or misconfigured.
    """
    min_interval = 1.0 / settings.REVERSE_GEO_RATE_LIMIT if settings.REVERSE_GEO_RATE_LIMIT > 0 else 0.0
    user_agent = f"Endurain/{core_config.API_VERSION} (ReverseGeocoding)"
    provider = settings.REVERSE_GEO_PROVIDER

    if provider not in _GEOCODING_SERVICES:
        logger.warning(
            f"REVERSE_GEO_PROVIDER {provider!r} is not a supported service "
            f"(expected one of: {', '.join(_GEOCODING_SERVICES)}); "
            "reverse geocoding is disabled and activities will have no location",
            extra=core_logger.context(console=True),
        )
        return NullGeocoding()

    if provider == "geocode":
        if settings.GEOCODES_MAPS_API == "changeme":
            logger.warning(
                "REVERSE_GEO_PROVIDER is 'geocode' but GEOCODES_MAPS_API is still the "
                "'changeme' placeholder; reverse geocoding is disabled and activities "
                "will have no location",
                extra=core_logger.context(console=True),
            )
            return NullGeocoding()
        # Fixed, vendor-operated host — nothing operator-supplied to validate.
        base_url = "https://geocode.maps.co/reverse"
        api_key = settings.GEOCODES_MAPS_API
    else:
        if provider == "nominatim":
            host, use_https = settings.NOMINATIM_API_HOST, settings.NOMINATIM_API_USE_HTTPS
        else:
            host, use_https = settings.PHOTON_API_HOST, settings.PHOTON_API_USE_HTTPS
        # Logs its own reason when it rejects the host.
        base_url = build_reverse_endpoint(host, use_https=use_https)
        if base_url is None:
            return NullGeocoding()
        api_key = None

    logger.info(
        f"Reverse geocoding enabled via {provider} ({base_url}), rate limit {settings.REVERSE_GEO_RATE_LIMIT}/s",
        extra=core_logger.context(console=True),
    )
    return HttpGeocoding(
        provider,
        base_url,
        api_key=api_key,
        min_interval_seconds=min_interval,
        user_agent=user_agent,
    )
