"""FastAPI dependencies exposing the platform providers to routes and handlers.

The composition root attaches the assembled ``Platform`` to
``app.state.platform`` at startup; these thin dependencies read it back so
routes depend on providers (via ``Depends``) rather than importing backends.
"""

from fastapi import Request

from core.platform.container import Platform
from core.platform.providers import ClockProvider, EventBusProvider, LockProvider, StateProvider, StorageProvider


def get_platform(request: Request) -> Platform:
    """Return the process-wide ``Platform`` from application state."""
    return request.app.state.platform


def get_state(request: Request) -> StateProvider:
    """Return the ephemeral-state provider."""
    return request.app.state.platform.state


def get_storage(request: Request) -> StorageProvider:
    """Return the blob-storage provider."""
    return request.app.state.platform.storage


def get_events(request: Request) -> EventBusProvider:
    """Return the event-bus provider."""
    return request.app.state.platform.events


def get_lock(request: Request) -> LockProvider:
    """Return the coordination-lock provider."""
    return request.app.state.platform.lock


def get_clock(request: Request) -> ClockProvider:
    """Return the clock provider."""
    return request.app.state.platform.clock
