import contextlib
from collections.abc import Callable, Iterator
from datetime import UTC, datetime, timedelta

import httpx2
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pwdlib.hashers.argon2 import Argon2Hasher
from sqlalchemy.orm import Session, sessionmaker

import core.database as core_database
import modules.auth.access_tokens.service as auth_token_manager
import modules.auth.credentials.integration_service as auth_password_hasher
import modules.auth.credentials.password_hasher as credentials_password_hasher
import modules.server_settings.contracts as server_settings_contracts
import modules.users.contributor_registry as users_contributor_registry
import modules.users.users.schema as user_schema
from tests._factories import auth as auth_factories
from tests._helpers import database as test_database
from tests._helpers.auth import MOCK_USER_ID

#: The hasher the application ships with, kept for the test that pins its Argon2 cost.
PRODUCTION_PASSWORD_HASHER = credentials_password_hasher.password_hasher


@pytest.fixture(scope="session", autouse=True)
def _low_cost_password_hashing() -> Iterator[None]:
    """Hash with Argon2 at a low cost: the same algorithm and code, without 64 MiB and several passes per hash.

    Every sign-in, step-up and password change hashes or verifies, and parallel workers running the production cost
    starve each other of CPU. A stored hash carries its own parameters, so verification is unchanged.
    ``tests/auth/credentials/test_password_hasher.py`` pins the production cost.
    """
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(
            credentials_password_hasher,
            "password_hasher",
            credentials_password_hasher.PasswordHasher(
                hasher=[Argon2Hasher(time_cost=1, memory_cost=1024, parallelism=1)]
            ),
        )
        yield


@pytest.fixture(autouse=True)
def _no_breach_range_requests(monkeypatch):
    """Keep a test from reaching the real breach range API: every range request answers with no matches.

    A test of the breached-password check patches ``httpx2.get`` itself.
    """

    def no_matches(url, *_args, **_kwargs):
        return httpx2.Response(200, text="", request=httpx2.Request("GET", url))

    monkeypatch.setattr(httpx2, "get", no_matches)


def _uses_real_database(request: pytest.FixtureRequest) -> bool:
    """Return whether the test runs on the real PostgreSQL database, so it runs as production does.

    Every fixture that gives a test that database depends on ``_worker_database``, which no module shadows, unlike
    a name such as ``db``.
    """
    return "_worker_database" in request.fixturenames


@pytest.fixture(autouse=True)
def _publish_local_platform(tmp_path, request):
    """Publish a fresh in-process ``Platform`` for every test.

    The auth/garmin/websocket store singletons resolve ``platform.state`` lazily
    through ``jasil.runtime`` (production sets it at startup). A fresh platform
    per test keeps the in-memory state isolated, and ``reset_all`` clears every
    other process-wide slot JASIL installs so one test cannot leak into the next.
    The ORM mapping is deliberately left alone — ``core.database`` maps it once
    at import and the model modules capture the base then.

    The audit catalog is registered as the entrypoints register it. A test on the real database writes audit rows in
    its transaction, as production does; any other test runs with writes off, and ``jasil.testing.capture_audit``
    still sees every row it stages.

    A test on the real database starts its fixed clock at the current time: the audit log is partitioned by day and
    the migrations create the partitions around the day they run, as in production. It also gets the wiring every
    API and worker process installs (``module_registry.configure_application``).
    """
    import jasil.settings as jasil_settings
    import jasil.testing as jasil_testing

    import module_registry as runtime_module_registry

    real_database = _uses_real_database(request)
    audit = jasil_settings.AuditSettings(enabled=real_database)
    clock = jasil_testing.FixedClock(datetime.now(UTC)) if real_database else None
    platform = jasil_testing.install_test_platform(
        tmp_path, clock=clock, settings=jasil_settings.JasilSettings(audit=audit)
    )
    if real_database:
        # What every API and worker process installs before it runs work.
        runtime_module_registry.configure_application()
    else:
        runtime_module_registry.configure_audit()
    yield platform
    if real_database:
        users_contributor_registry.clear()
    jasil_testing.reset_all()


@pytest.fixture(scope="session")
def _worker_database() -> Iterator[None]:
    """Clone this process's database from the migrated template for the session, and drop it afterwards.

    A test that needs the database fails, rather than skips, when the run has none.
    """

    try:
        test_database.create_worker_database()
    except RuntimeError as err:
        pytest.fail(str(err), pytrace=False)
    yield
    core_database.engine.dispose()
    test_database.drop_process_databases()


@pytest.fixture
def db(_worker_database) -> Iterator[Session]:
    """A session on the worker database, inside a transaction that is rolled back after the test.

    The application's ``SessionLocal`` is bound to the same connection for the test, with every session it opens
    joining the test's transaction through a savepoint: a route's session, a service's own session and the session a
    factory writes with all see each other's rows, and a ``commit()`` in the code under test ends only its savepoint.
    Nothing reaches the database for the next test.

    For queries, constraints and in-process crud and service work. Because every session shares one transaction, a
    rollback also discards what another session committed meanwhile (a ``record_detached`` audit row, for one), which
    production keeps. So a test of what survives a failure, of refusals and their audit rows, of isolation between
    sessions, row locks, races, or of code on another thread uses ``committed_sessions``, as the HTTP fixtures do.
    """

    with test_database.rolled_back_session(core_database.engine, core_database.SessionLocal) as session:
        yield session


@pytest.fixture
def committed_sessions(_worker_database) -> Iterator[sessionmaker[Session]]:
    """The application's own session factory on the worker database, with real commits on separate connections.

    Every session has its own connection and transaction, as in production: what one commits survives another's
    rollback. The worker database is cloned again from the template after the test, so what it committed is gone for
    the next one.
    """

    try:
        yield core_database.SessionLocal
    finally:
        test_database.reset_worker_database(core_database.engine)


@contextlib.contextmanager
def _preserved_loggers() -> Iterator[None]:
    """Restore the loggers application setup configures, so a test that builds the app leaves logging as it was."""
    import logging

    import core.logger as core_logger

    loggers = [
        logging.getLogger(name)
        for name in (core_logger.ROOT_LOGGER_NAME, "alembic", "apscheduler", "safeuploads.audit", "slowapi")
    ]
    loggers.append(logging.getLogger("uvicorn.error"))
    saved = [(lg, list(lg.handlers), lg.level, lg.propagate, list(lg.filters)) for lg in loggers]
    try:
        yield
    finally:
        for lg, handlers, level, propagate, filters in saved:
            lg.handlers[:] = handlers
            lg.setLevel(level)
            lg.propagate = propagate
            lg.filters[:] = filters


@pytest.fixture
def app_log(caplog) -> Iterator[pytest.LogCaptureFixture]:
    """Capture every record of the application's logger once, at every level.

    The records reach caplog through its handler alone: the logger stops propagating meanwhile, so a record is not
    captured a second time through the root logger in a process where application setup has not turned propagation
    off.
    """
    import logging

    import core.logger as core_logger

    logger = logging.getLogger(core_logger.ROOT_LOGGER_NAME)
    level, propagate = logger.level, logger.propagate
    logger.addHandler(caplog.handler)
    logger.setLevel(logging.DEBUG)
    logger.propagate = False
    try:
        yield caplog
    finally:
        logger.propagate = propagate
        logger.setLevel(level)
        logger.removeHandler(caplog.handler)


@pytest.fixture
def app(committed_sessions, _publish_local_platform, tmp_path, monkeypatch) -> Iterator[FastAPI]:
    """The production application, built by ``main.create_app`` and wired as startup wires it, on the test database.

    Real middleware, routes under ``/api/v1``, exception handlers, authentication and scope checks; nothing is
    overridden. Requests commit for real (``committed_sessions``): a test arranges its rows in a session it commits,
    and reads the outcome back in a new one. The lifespan does not run, so there are no migrations, scheduler,
    provider syncs or DNS lookups, and no bus subscribers: a test that needs a subscriber's effect registers it. The
    directories startup creates are under the test's temporary directory.
    """
    import core.config as core_config

    data_dir = tmp_path / "data"
    monkeypatch.setattr(core_config.settings, "DATA_DIR", str(data_dir))
    monkeypatch.setattr(core_config.settings, "LOGS_DIR", str(tmp_path / "logs"))
    monkeypatch.setattr(core_config.settings, "FILES_DIR", str(data_dir / "activity_files"))
    for name in ("SERVER_IMAGES_DIR", "FILES_PROCESSED_DIR", "FILES_BULK_IMPORT_DIR", "FILES_UPLOAD_INCOMING_DIR"):
        monkeypatch.setattr(core_config, name, str(data_dir / name.lower()))
    # The pre-flight requires the variable; the settings already hold its value.
    monkeypatch.setenv("ENDURAIN_HOST", core_config.settings.ENDURAIN_HOST)
    with _preserved_loggers():
        # ``main`` builds its module-level app on first import, so that import runs under the same settings.
        import main

        application = main.create_app()
        main.attach_platform(application, _publish_local_platform)
        yield application


@pytest.fixture
def client(app) -> TestClient:
    """An anonymous HTTP client for the production application; ``sign_in`` gives an authenticated one."""
    return TestClient(app)


@pytest.fixture
def sign_in(app, committed_sessions) -> Callable[[user_schema.UserRead], auth_factories.SignedIn]:
    """Return a function that signs a committed user in as a web client of the production application."""

    def signed_in(user: user_schema.UserRead) -> auth_factories.SignedIn:
        with committed_sessions() as session:
            return auth_factories.sign_in(app, session, user)

    return signed_in


@pytest.fixture
def password_hasher() -> auth_password_hasher.PasswordHasher:
    """
    Creates and returns an instance of auth_password_hasher.PasswordHasher using the get_password_hasher function.

    Returns:
        auth_password_hasher.PasswordHasher: An instance of the password hasher utility.
    """
    return auth_password_hasher.get_password_hasher()


@pytest.fixture
def session_policy() -> server_settings_contracts.SessionPolicy:
    """The default session policy: 15-minute access, 7-day refresh, no idle timeout, 30-day absolute timeout."""
    return server_settings_contracts.SessionPolicy(
        access_token_ttl=timedelta(minutes=15),
        refresh_token_ttl=timedelta(days=7),
        idle_timeout=None,
        absolute_timeout=timedelta(hours=720),
        api_key_max_lifetime=timedelta(days=365),
    )


@pytest.fixture
def token_manager() -> auth_token_manager.TokenManager:
    """A token manager with one test key for access tokens and another for refresh tokens."""
    return auth_token_manager.TokenManager(
        access_keys=["test-access-key-for-testing-only-min-32-chars"],
        refresh_keys=["test-refresh-key-for-testing-only-min-32-chars"],
    )


@pytest.fixture
def sample_user_read() -> user_schema.UserRead:
    """
    Creates and returns a sample instance of UserRead for testing purposes.

    Returns:
        user_schema.UserRead: A sample user object with predefined attributes.
    """
    return user_schema.UserRead(
        id=MOCK_USER_ID,
        name="Test User",
        username="testuser",
        email="test@example.com",
        active=True,
        access_type=user_schema.UserAccessType.REGULAR.value,
    )
