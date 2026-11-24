"""Fixtures for the ingestion tests: the in-process pool that runs jobs on the local profile, and signed-in users."""

import dataclasses
import threading
from collections.abc import Callable, Iterator
from concurrent.futures import Future

import jasil.jobs.registry as jobs_registry
import jasil.runtime as jasil_runtime
import jasil.settings as jasil_settings
import jasil.testing as jasil_testing
import pytest

import core.config as core_config
import core.local_pool as core_local_pool
import modules.activities.activity_ingestion.background as ingestion_background
import modules.activities.activity_ingestion.provider_registry as ingestion_provider_registry
import modules.activities.activity_ingestion.subscribers as ingestion_subscribers
from tests._factories.ingestion import StubProvider
from tests._factories.profile import FaultyStorage


class DrainedPool(core_local_pool.BoundedPool):
    """The ingestion pool of the local profile, whose jobs a test waits for instead of polling.

    Attributes:
        futures: Every job the pool was given, in order.
    """

    def __init__(self, *, workers: int = 2, max_pending: int = 100) -> None:
        """Build a pool of the production shape.

        Args:
            workers: Jobs that run at once.
            max_pending: Jobs held at once, running and queued.
        """
        super().__init__("test-ingestion", workers=workers, max_pending=max_pending)
        self.futures: list[Future] = []
        self._recorded = threading.Lock()

    def submit_waiting(self, wait_seconds, run, /, *args, **kwargs):
        """Run a job as the pool does, remembering its future."""
        future = super().submit_waiting(wait_seconds, run, *args, **kwargs)
        with self._recorded:
            self.futures.append(future)
        return future

    def drain(self) -> None:
        """Wait until every job given so far has finished; a job that raised is logged by the pool, not here."""
        with self._recorded:
            pending = list(self.futures)
        for future in pending:
            future.exception(timeout=30)


@pytest.fixture
def pool(committed_sessions, monkeypatch) -> Iterator[DrainedPool]:
    """The ingestion pool replaced by one a test can drain, shut down before the database is reset."""
    drained = DrainedPool()
    monkeypatch.setattr(ingestion_background, "_pool", drained)
    yield drained
    drained.shutdown(wait=True)


@pytest.fixture
def make_signed_in(committed_sessions, sign_in) -> Callable:
    """Return a function that commits a user and signs it in as a web client."""
    from tests._factories.users import make_user

    def make(**options):
        options.setdefault("timezone", "UTC")
        with committed_sessions() as db:
            user = make_user(db, **options)
            db.commit()
        return sign_in(user)

    return make


@pytest.fixture
def platform(_publish_local_platform):
    """The test platform: real local storage under the test's directory, the fixed clock and the realtime hints."""
    return _publish_local_platform


@pytest.fixture
def storage(platform):
    """The platform's storage, where uploads are staged and activity files retained."""
    return platform.storage


@pytest.fixture
def hints(platform) -> list[tuple[str, dict]]:
    """The realtime hints pushed during the test, as ``(key, hint)`` in order."""
    return jasil_testing.capture_hints(platform)


@pytest.fixture
def durable_jobs(monkeypatch) -> None:
    """Run the test on the durable profile: jobs are staged in the outbox for a worker, never run in-process."""
    monkeypatch.setattr(core_config.settings, "JOBS_ENABLED", True)
    settings = jasil_settings.get_settings()
    jasil_settings.configure(dataclasses.replace(settings, jobs=dataclasses.replace(settings.jobs, enabled=True)))
    ingestion_subscribers.register_durable_handlers(jobs_registry.registry)


@pytest.fixture
def break_storage(platform) -> Callable[..., FaultyStorage]:
    """Return a function that makes the platform's storage fail the way an unreachable backend does.

    The routes and the jobs they start resolve the storage from the active platform, so the failure reaches them as
    it would in production. The real storage underneath keeps answering every method no fault names.
    """

    def apply(**faults: BaseException) -> FaultyStorage:
        faulty = FaultyStorage(platform.storage, faults=faults)
        jasil_runtime.set_active_platform(dataclasses.replace(platform, storage=faulty))
        return faulty

    return apply


@pytest.fixture
def providers() -> Iterator[None]:
    """An empty provider registry for the test, so only the providers it registers are asked."""
    ingestion_provider_registry.clear()
    yield
    ingestion_provider_registry.clear()


@pytest.fixture
def stub_provider(providers) -> StubProvider:
    """A registered provider with no linked user."""
    return StubProvider().register()
