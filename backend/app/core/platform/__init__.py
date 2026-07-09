"""Platform substrate: deployment profile, event envelope, and providers.

Public (pure) surface — safe to import anywhere; pulls in no backends:
    - ``DeploymentProfile`` — the deployment shape.
    - ``Event`` / ``new_event`` — the event envelope.
    - ``StateProvider`` / ``StorageProvider`` / ``EventBusProvider`` /
      ``LockProvider`` / ``ClockProvider`` — the capability providers.

The composition root (``Platform`` / ``build_platform``) lives in
``core.platform.container`` and is imported explicitly where the platform is
built (startup, ``deps``). Keeping it out of this ``__init__`` means importing
the pure profile/capabilities modules — e.g. from ``core.config`` at import
time — never drags the concrete backends in.
"""

from core.platform.events import Event, new_event
from core.platform.profile import DeploymentProfile
from core.platform.providers import (
    ClockProvider,
    EventBusProvider,
    LockProvider,
    StateBackendUnavailableError,
    StateProvider,
    StorageProvider,
    TieredFailureOutcome,
)

__all__ = [
    "ClockProvider",
    "DeploymentProfile",
    "Event",
    "EventBusProvider",
    "LockProvider",
    "StateBackendUnavailableError",
    "StateProvider",
    "StorageProvider",
    "TieredFailureOutcome",
    "new_event",
]
