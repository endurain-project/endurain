"""Fixtures shared by the Garmin Connect tests: a fake Garmin Connect account, linked users and the module's pools."""

import threading
import time
import uuid
from collections.abc import Callable, Iterator
from typing import Any

import jasil.runtime as jasil_runtime
import jasil.testing as jasil_testing
import pytest
from jasil.providers import StateBackendUnavailableError
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

import core.local_pool as core_local_pool
import core.sync_runner as core_sync_runner
import modules.garmin.link_service as garmin_link_service
import modules.garmin.link_state_store as garmin_link_state_store
import modules.garmin.mfa_code_store as garmin_mfa_code_store
import modules.garmin.sync_service as garmin_sync_service
import modules.garmin.sync_state_store as garmin_sync_state_store
import modules.garmin.token_utils as garmin_token_utils
import modules.notifications.models as notifications_models
import modules.users.users.schema as users_schema
import modules.users.users_integrations.models as user_integrations_models
from tests._factories import garmin as garmin_factories
from tests._factories.users import make_user


class UnavailableState:
    """A ``StateProvider`` whose backend is down: every operation raises ``StateBackendUnavailableError``."""

    def __getattr__(self, name: str) -> Callable[..., Any]:
        def refuse(*_args: Any, **_kwargs: Any) -> Any:
            raise StateBackendUnavailableError("down")

        return refuse


@pytest.fixture
def account(monkeypatch) -> garmin_factories.GarminAccount:
    """A Garmin Connect account every client the module builds talks to."""
    return garmin_factories.GarminAccount().install(monkeypatch)


@pytest.fixture
def make_linked(committed_sessions) -> Callable[..., users_schema.UserRead]:
    """Return a function that commits a user with Garmin Connect linked, with the options of ``link_garmin``."""

    def make(**link_options: Any) -> users_schema.UserRead:
        with committed_sessions() as db:
            user = make_user(db, timezone="UTC")
            garmin_factories.link_garmin(db, user.id, **link_options)
            db.commit()
        return user

    return make


@pytest.fixture
def linked(make_linked) -> users_schema.UserRead:
    """A committed user with Garmin Connect linked."""
    return make_linked()


@pytest.fixture
def unlinked(committed_sessions) -> users_schema.UserRead:
    """A committed user who has not linked Garmin Connect."""
    with committed_sessions() as db:
        user = make_user(db, timezone="UTC")
        db.commit()
    return user


@pytest.fixture
def mfa_codes() -> garmin_mfa_code_store.GarminMFACodeStore:
    """The MFA code store over the platform state, as the routes build it."""
    return garmin_mfa_code_store.GarminMFACodeStore(jasil_runtime.get_state())


@pytest.fixture
def link_states() -> garmin_link_state_store.GarminLinkStateStore:
    """The link state store over the platform state, as the routes build it."""
    return garmin_link_state_store.GarminLinkStateStore(jasil_runtime.get_state())


@pytest.fixture
def sync_states() -> garmin_sync_state_store.GarminSyncStateStore:
    """The sync state store over the platform state, as the routes build it."""
    return garmin_sync_state_store.GarminSyncStateStore(jasil_runtime.get_state())


@pytest.fixture
def rate_limits():
    """The rate-limit store over the platform state, as the routes build it."""
    return garmin_factories.rate_limits()


@pytest.fixture
def hints() -> list[tuple[str, dict]]:
    """The realtime hints pushed during the test, as ``(key, hint)`` in order."""
    return jasil_testing.capture_hints(jasil_runtime.get_active_platform())


@pytest.fixture
def no_waiting(monkeypatch) -> list[float]:
    """Make ``time.sleep`` return at once and record the waits, so a test never waits on the real clock."""
    waits: list[float] = []
    monkeypatch.setattr(time, "sleep", waits.append)
    return waits


class BlockedPools:
    """Builds pools whose jobs hold their slot until ``release`` is set.

    Attributes:
        release: Set to let every held job finish.
    """

    def __init__(self) -> None:
        """Start with no pool and the jobs held."""
        self.release = threading.Event()
        self.pools: list[core_local_pool.BoundedPool] = []

    def __call__(self, max_pending: int) -> core_local_pool.BoundedPool:
        """Build a pool of the given size, with one worker per slot.

        Args:
            max_pending: Jobs the pool holds at once.

        Returns:
            The pool.
        """
        pool = core_local_pool.BoundedPool("test-garmin", workers=max_pending, max_pending=max_pending)
        self.pools.append(pool)
        return pool

    def with_held_worker(self, max_pending: int) -> core_local_pool.BoundedPool:
        """Build a one-worker pool whose worker is held, so the jobs submitted next wait queued.

        Args:
            max_pending: Jobs the pool holds at once, the held one included.

        Returns:
            The pool.
        """
        pool = core_local_pool.BoundedPool("test-garmin", workers=1, max_pending=max_pending)
        self.pools.append(pool)
        pool.submit(self.release.wait, 10)
        return pool


@pytest.fixture
def blocked_pool(committed_sessions) -> Iterator[BlockedPools]:
    """Build pools whose jobs hold their slot until the test releases them; drained before the database is reset."""
    pools = BlockedPools()
    yield pools
    pools.release.set()
    for pool in pools.pools:
        pool.shutdown(wait=True)


class _ClosedPool(core_local_pool.BoundedPool):
    """A pool whose executor is gone, as it is when the interpreter shuts down: it has room but runs nothing."""

    def submit_waiting(self, wait_seconds, run, /, *args, **kwargs):
        raise RuntimeError("cannot schedule new futures after shutdown")


@pytest.fixture
def closed_pool() -> core_local_pool.BoundedPool:
    """A pool that has room and refuses every job with the error an executor raises once it is shut down."""
    return _ClosedPool("test-garmin-closed", workers=1, max_pending=10)


@pytest.fixture
def link_pool(committed_sessions, monkeypatch) -> Iterator[core_local_pool.BoundedPool]:
    """The login pool of the module, replaced by a fresh one that is drained before the database is reset."""
    pool = core_sync_runner.link_pool("test-garmin-link")
    monkeypatch.setattr(garmin_link_service, "_link_pool", pool)
    yield pool
    pool.shutdown(wait=True)


@pytest.fixture
def sync_pool(committed_sessions, monkeypatch) -> Iterator[core_local_pool.BoundedPool]:
    """The sync pool of the module, replaced by a fresh one that is drained before the database is reset."""
    pool = core_sync_runner.sync_pool("test-garmin-sync")
    monkeypatch.setattr(garmin_sync_service, "_sync_pool", pool)
    yield pool
    pool.shutdown(wait=True)


def stored_token(sessions: sessionmaker[Session], user_id: uuid.UUID) -> dict[str, Any] | None:
    """Read a user's stored Garmin Connect token back in a new session.

    Args:
        sessions: The application's session factory.
        user_id: The token's owner.

    Returns:
        The token as stored (secrets encrypted), or ``None`` when Garmin Connect is not linked.
    """
    with sessions() as db:
        return db.scalars(
            select(user_integrations_models.UsersIntegrations.garminconnect_token).where(
                user_integrations_models.UsersIntegrations.user_id == user_id
            )
        ).one()


def stored_access_token(sessions: sessionmaker[Session], user_id: uuid.UUID) -> str | None:
    """Read a user's stored access token back and decrypt it, or ``None`` when Garmin Connect is not linked."""
    token = stored_token(sessions, user_id)
    return None if token is None else _decrypted(token)["di_token"]


def _decrypted(token: dict[str, Any]) -> dict[str, Any]:
    import json

    return json.loads(garmin_token_utils.deserialize_garmin_token(token))


def notifications_of(sessions: sessionmaker[Session], user_id: uuid.UUID) -> list[notifications_models.Notification]:
    """List a user's committed notifications, oldest first."""
    with sessions() as db:
        return list(
            db.scalars(
                select(notifications_models.Notification)
                .where(notifications_models.Notification.user_id == user_id)
                .order_by(notifications_models.Notification.created_at)
            )
        )
