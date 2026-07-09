"""Process-wide access to the assembled ``Platform`` for non-request contexts.

FastAPI handlers reach the platform through ``core.platform.deps`` (which reads
``request.app.state.platform``). Background work — the scheduler, the Garmin
login thread — has no request, so the composition root also publishes the active
``Platform`` here at startup via :func:`set_active_platform`. Stores that must
work in both contexts resolve their provider lazily through :func:`get_state`.
"""

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from core.platform.container import Platform
    from core.platform.providers import StateProvider

_active_platform: "Platform | None" = None


def set_active_platform(platform: "Platform") -> None:
    """Publish the assembled platform for process-wide access.

    Called once from lifespan startup after ``build_platform``.

    Args:
        platform: The assembled platform substrate.

    Raises:
        None.
    """
    global _active_platform
    _active_platform = platform


def get_active_platform() -> "Platform":
    """Return the process-wide platform, or fail if startup has not run.

    Returns:
        The active platform substrate.

    Raises:
        RuntimeError: When no platform has been published yet.
    """
    if _active_platform is None:
        raise RuntimeError("Platform is not initialized; build_platform must run at startup before this is used.")
    return _active_platform


def get_state() -> "StateProvider":
    """Return the process-wide ephemeral-state provider.

    Returns:
        The active ``StateProvider``.

    Raises:
        RuntimeError: When no platform has been published yet.
    """
    return get_active_platform().state
