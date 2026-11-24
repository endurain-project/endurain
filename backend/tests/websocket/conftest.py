"""Fixtures for the websocket tests: a process that holds sockets, as the API process does."""

from collections.abc import Iterator

import anyio.from_thread
import jasil.runtime as jasil_runtime
import pytest
from fastapi.testclient import TestClient

import core.async_bridge as core_async_bridge
import modules.websocket.manager as websocket_manager
import modules.websocket.subscriber_registry as websocket_subscriber_registry


@pytest.fixture(autouse=True)
def _fresh_connection_registry() -> Iterator[None]:
    """Give every test its own connection registry and leave no main loop behind."""
    websocket_manager.get_websocket_manager.cache_clear()
    yield
    core_async_bridge.set_main_loop(None)
    websocket_manager.get_websocket_manager.cache_clear()


@pytest.fixture
def holding_client(app) -> Iterator[TestClient]:
    """A client of the production application whose sockets live on one event loop that is the process's main loop.

    The application subscribes to the realtime channel and hands a hint to the main loop, which owns the sockets.
    A ``TestClient`` outside a ``with`` block starts a loop per request, so this one shares a single portal across
    its requests and connections and records its loop as the main loop, as the lifespan does. The channel is
    subscribed as the lifespan subscribes it.
    """
    with anyio.from_thread.start_blocking_portal() as portal:
        portal.call(core_async_bridge.capture_running_loop)
        realtime = jasil_runtime.get_active_platform().realtime
        websocket_subscriber_registry.register_realtime_subscribers(realtime)
        realtime.start()
        client = TestClient(app)
        client.portal = portal
        yield client
