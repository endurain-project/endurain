"""Shared fixtures for the Garmin Connect tests."""

import threading

import pytest

import core.local_pool as core_local_pool
import modules.garmin.token_utils as garmin_token_utils


@pytest.fixture
def blocked_pool():
    """Build a pool of the given size whose jobs hold their slot until the test releases them."""
    release = threading.Event()
    pools: list[core_local_pool.BoundedPool] = []

    def build(max_pending: int) -> core_local_pool.BoundedPool:
        pool = core_local_pool.BoundedPool("test-garmin", workers=max_pending, max_pending=max_pending)
        pools.append(pool)
        return pool

    build.release = release
    yield build
    release.set()
    for pool in pools:
        pool.shutdown(wait=True)


@pytest.fixture(autouse=True)
def _live_tokens(monkeypatch):
    """Treat restored tokens as live, so a test that does not mean to refresh never takes the refresh claim."""
    monkeypatch.setattr(garmin_token_utils, "expires_soon", lambda client: False)
