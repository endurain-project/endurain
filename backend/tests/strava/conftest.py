import dataclasses
from collections.abc import Callable, Iterator

import jasil.jobs.registry as jobs_registry
import jasil.runtime as platform_runtime
import jasil.settings as jasil_settings
import pytest

import core.config as core_config
import modules.strava.rate_limit_store as strava_rate_limit_store
import modules.strava.subscribers as strava_subscribers
from tests._factories import strava as strava_factories
from tests._helpers.clock import platform_clock


@pytest.fixture
def strava(monkeypatch: pytest.MonkeyPatch) -> Iterator[strava_factories.FakeStrava]:
    """Replace the network under ``requests`` with a fake Strava, and check nothing unarranged was called."""
    fake = strava_factories.FakeStrava()
    fake.install(monkeypatch)
    yield fake
    assert fake.unrouted == [], f"Strava was called without an arranged answer: {fake.unrouted}"


@pytest.fixture
def advance_state_clock() -> Callable[[float], None]:
    """Return a function that moves the platform clock the in-memory state store expires keys by, unslept."""
    return platform_clock().advance


@pytest.fixture
def rate_limits() -> strava_rate_limit_store.StravaRateLimitStore:
    """The Strava rate-limit store over the platform state, as a sync gets it."""
    return strava_rate_limit_store.StravaRateLimitStore(platform_runtime.get_state())


@pytest.fixture
def durable_jobs(monkeypatch: pytest.MonkeyPatch) -> None:
    """Run the test on the durable profile: syncs are staged in the outbox for a worker, never run in-process."""
    monkeypatch.setattr(core_config.settings, "JOBS_ENABLED", True)
    settings = jasil_settings.get_settings()
    jasil_settings.configure(dataclasses.replace(settings, jobs=dataclasses.replace(settings.jobs, enabled=True)))
    strava_subscribers.register_durable_handlers(jobs_registry.registry)
