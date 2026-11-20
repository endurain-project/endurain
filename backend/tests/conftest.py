import contextlib
import uuid
from collections.abc import Callable, Iterator
from datetime import UTC, datetime, timedelta
from importlib import import_module
from unittest.mock import MagicMock

import httpx2
import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient
from sqlalchemy import CursorResult
from sqlalchemy.orm import Session, sessionmaker

import core.database as core_database
import core.exceptions as core_exceptions
import modules.auth.access_tokens.integration_service as access_tokens_integration
import modules.auth.access_tokens.service as auth_token_manager
import modules.auth.authentication.dependencies as authentication_dependencies
import modules.auth.constants as auth_constants
import modules.auth.contracts as auth_contracts
import modules.auth.credentials.integration_service as auth_password_hasher
import modules.auth.dependencies as auth_dependencies
import modules.auth.mfa.dependencies as auth_mfa_dependencies
import modules.auth.security_generation.integration_service as security_generation_integration
import modules.server_settings.contracts as server_settings_contracts
import modules.users.contributor_registry as users_contributor_registry
import modules.users.users.schema as user_schema
from tests._factories import auth as auth_factories
from tests._helpers import database as test_database
from tests._helpers.auth import MOCK_USER_ID, OTHER_USER_ID
from tests._helpers.security_generation import FakeSecurityGenerations

#: The id of the session the test app's overridden principal and token overrides carry.
MOCK_SESSION_ID = uuid.UUID("00000000-0000-4000-8000-0000000000a1")

#: The routers the legacy ``fast_api_app`` mounts, under the prefixes its tests call. New tests use ``app``.
_LEGACY_ROUTERS = (
    ("modules.health.health_sleep.router", "/health_sleep"),
    ("modules.health.health_steps.router", "/health_steps"),
    ("modules.health.health_targets.router", "/health/targets"),
    ("modules.health.health_weight.router", "/health_weight"),
    ("modules.users.users_goals.router", "/user_goals"),
    ("modules.auth.account_security.api_keys_router", "/api-keys"),
    ("modules.auth.account_security.devices_router", "/devices"),
    ("modules.auth.account_security.admin_api_keys_router", "/users"),
    ("modules.server_settings.router", "/server_settings"),
)

#: The routers the legacy ``fast_api_app_public`` mounts.
_LEGACY_PUBLIC_ROUTERS = (("modules.server_settings.public_router", "/server_settings/public"),)


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


@pytest.fixture(autouse=True)
def security_generations(monkeypatch, request) -> FakeSecurityGenerations | None:
    """Replace the account security generations with an in-memory store, so a mocked session can stamp and check.

    A test on the real database keeps the real generations and gets ``None``. The tests of the generations
    themselves override this fixture.
    """
    if _uses_real_database(request):
        return None
    fake = FakeSecurityGenerations()
    monkeypatch.setattr(security_generation_integration, "current_generation", fake.current_generation)
    monkeypatch.setattr(security_generation_integration, "stage_bump", fake.stage_bump)
    monkeypatch.setattr(security_generation_integration, "matches_locked", fake.matches_locked)
    return fake


@pytest.fixture(scope="session")
def _worker_database() -> Iterator[None]:
    """Clone this process's database from the migrated template for the session, and drop it afterwards.

    A test that needs the database fails, rather than skips, when the run has none.
    """
    import core.database as core_database

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
    import core.database as core_database

    with test_database.rolled_back_session(core_database.engine, core_database.SessionLocal) as session:
        yield session


@pytest.fixture
def committed_sessions(_worker_database) -> Iterator[sessionmaker[Session]]:
    """The application's own session factory on the worker database, with real commits on separate connections.

    Every session has its own connection and transaction, as in production: what one commits survives another's
    rollback. The worker database is cloned again from the template after the test, so what it committed is gone for
    the next one.
    """
    import core.database as core_database

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
def mock_db() -> MagicMock:
    """
    Creates and returns a MagicMock object that mimics the interface of a SQLAlchemy Session.

    Returns:
        MagicMock: A mock object with the specification of a SQLAlchemy Session.
    """
    db = MagicMock(spec=Session)
    # A DML statement yields a CursorResult, which carries the row count; it also answers every Result read.
    db.execute.return_value = MagicMock(spec=CursorResult)
    # A real savepoint rolls back and re-raises; a bare mock context manager would swallow the error.
    db.begin_nested.return_value.__exit__.return_value = False
    return db


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


@pytest.fixture
def sample_inactive_user():
    """
    Creates and returns a sample inactive user instance for testing purposes.

    Returns:
        user_schema.UserRead: An instance representing an inactive user with predefined attributes.
    """
    return user_schema.UserRead(
        id=OTHER_USER_ID,
        name="Inactive User",
        username="inactive",
        email="inactive@example.com",
        active=False,
        access_type=user_schema.UserAccessType.REGULAR.value,
    )


@pytest.fixture
def mock_request() -> Request:
    """
    Creates and returns a mock Request object with predefined headers and client host.

    Returns:
        Request: A MagicMock instance mimicking a Request object, with custom headers and client host set for testing
            purposes.
    """
    mock_req = MagicMock(spec=Request)
    mock_req.headers = {
        "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "X-Client-Type": "web",
    }
    mock_req.client = MagicMock()
    mock_req.client.host = "127.0.0.1"
    return mock_req


def _include_routers(app: FastAPI, routers: tuple[tuple[str, str], ...]) -> None:
    """Mount each router under its prefix; a router that cannot be imported fails the test."""
    for dotted, prefix in routers:
        app.include_router(import_module(dotted).router, prefix=prefix)


def _override_credentials_and_db(app: FastAPI, password_hasher, token_manager, mock_db) -> None:
    """Hand the app the test password hasher, token manager and mocked session."""
    app.dependency_overrides[auth_password_hasher.get_password_hasher] = lambda: password_hasher
    app.dependency_overrides[access_tokens_integration.get_token_manager] = lambda: token_manager
    app.dependency_overrides[core_database.get_db] = lambda: mock_db


@pytest.fixture
def fast_api_app(password_hasher, token_manager, mock_db) -> FastAPI:
    """
    Creates and configures a FastAPI application instance for testing purposes.
    This function sets up the FastAPI app with test-specific dependency overrides,
    including password hasher, token manager, and a mock database. It also injects
    a fake in-memory store for pending multi-factor authentication (MFA) attempts,
    and includes any default routers specified in the configuration.
        password_hasher: An object or callable used to hash passwords, typically a mock for testing.
        token_manager: An object or callable responsible for managing authentication tokens, typically a mock for
            testing.
        mock_db: A mock database session or connection to be used in place of the real database during tests.
        FastAPI: A configured FastAPI application instance with all test dependencies and routers included.
    """

    app = FastAPI()
    core_exceptions.register_exception_handlers(app)

    _include_routers(app, _LEGACY_ROUTERS)

    app.state._client_type = "web"

    def _client_type_override():
        return app.state._client_type

    class FakePendingMFAStore:
        """
        A fake in-memory store for tracking pending multi-factor authentication (MFA) login attempts.
        Primarily used for testing purposes to simulate the behavior of a pending MFA store.

        Attributes:
            calls (list): The user ID of each call to add_pending_login.
            _store (dict): Internal storage mapping challenges to user IDs for pending logins.

        Methods:
            add_pending_login(user_id):
            get_pending_login(challenge):
            claim_pending_login(challenge):
            delete_pending_login(challenge):
            clear_all():
        """

        def __init__(self):
            """
            Initializes the object and creates an empty list to store call records.
            """
            self.calls = []
            self._store = {}

        def add_pending_login(self, pending):
            """
            Adds a pending login and returns the challenge that names it.

            Args:
                pending (PendingLogin): The login that waits for its second factor.

            Returns:
                str: The challenge.
            """
            challenge = f"challenge-{len(self.calls)}"
            self.calls.append(pending.user_id)
            self._store[challenge] = pending
            return challenge

        def get_pending_login(self, username: str):
            """
            Retrieve the pending login information for a given username.

            Args:
                username (str): The username to look up.

            Returns:
                Any: The pending login information associated with the username, or None if not found.
            """
            return self._store.get(username)

        def claim_pending_login(self, username: str):
            """
            Retrieve and remove the pending login information for a username.

            Args:
                username (str): The username to claim.

            Returns:
                Any: The pending login information, or None if not found.
            """
            return self._store.pop(username, None)

        def delete_pending_login(self, username: str):
            """
            Removes the pending login entry for the specified username from the internal store.

            Args:
                username (str): The username whose pending login entry should be deleted.

            Returns:
                None
            """
            if username in self._store:
                del self._store[username]

        def record_wrong_code(self, challenge: str) -> bool:
            """
            Leave the challenge live; the cap is covered against the real store.

            Args:
                challenge (str): The challenge the wrong code was presented with.

            Returns:
                bool: Always False.
            """
            return False

        def clear_all(self):
            """
            Clears all pending login entries from the internal store.
            """
            self._store.clear()
            self.calls.clear()

    fake_store = FakePendingMFAStore()
    app.state.fake_store = fake_store

    # Create mock values for security dependencies
    app.state.mock_access_token = "mock_access_token"
    app.state.mock_refresh_token = "mock_refresh_token"
    app.state.mock_user_id = MOCK_USER_ID
    app.state.mock_session_id = MOCK_SESSION_ID

    # Security dependency overrides for testing authenticated endpoints
    def _mock_validate_access_token():
        """Mock validation that always passes"""
        return None

    def _mock_validate_refresh_token():
        """Mock validation that always passes"""
        return None

    def _mock_get_principal():
        """Return a signed-in caller holding every scope"""
        return auth_contracts.Principal(
            user_id=app.state.mock_user_id,
            username="mock-user",
            email="mock-user@example.com",
            is_active=True,
            is_superuser=False,
            scopes=frozenset(auth_constants.ADMIN_ACCESS_SCOPE),
            credential=auth_contracts.AccessTokenCred(session_id=app.state.mock_session_id),
        )

    def _mock_get_refresh_token():
        """Return mock refresh token"""
        return app.state.mock_refresh_token

    def _mock_get_sub_from_access_token():
        """Return mock user ID from access token"""
        return app.state.mock_user_id

    def _mock_get_sid_from_access_token():
        """Return mock session ID from access token"""
        return app.state.mock_session_id

    def _mock_get_sub_from_refresh_token():
        """Return mock user ID from refresh token"""
        return app.state.mock_user_id

    def _mock_get_sid_from_refresh_token():
        """Return mock session ID from refresh token"""
        return app.state.mock_session_id

    def _mock_get_exp_from_refresh_token():
        """Return a mock expiry from refresh token"""
        return datetime.now(UTC) + timedelta(days=7)

    def _mock_get_and_return_refresh_token():
        """Return mock refresh token"""
        return app.state.mock_refresh_token

    def _mock_check_scopes():
        """Mock scope check that always passes"""
        return None

    app.dependency_overrides[authentication_dependencies.get_client_type] = _client_type_override
    app.dependency_overrides[auth_mfa_dependencies.get_pending_mfa_store] = lambda: fake_store

    # Override auth-internal dependencies for auth router endpoint tests.
    app.dependency_overrides[authentication_dependencies.validate_refresh_token] = _mock_validate_refresh_token
    app.dependency_overrides[auth_dependencies.get_principal] = _mock_get_principal
    app.dependency_overrides[authentication_dependencies.get_refresh_token] = _mock_get_refresh_token
    app.dependency_overrides[auth_dependencies.get_current_user_id] = _mock_get_sub_from_access_token
    app.dependency_overrides[auth_dependencies.get_sid_from_access_token] = _mock_get_sid_from_access_token
    app.dependency_overrides[authentication_dependencies.get_sub_from_refresh_token] = _mock_get_sub_from_refresh_token
    app.dependency_overrides[authentication_dependencies.get_sid_from_refresh_token] = _mock_get_sid_from_refresh_token
    app.dependency_overrides[authentication_dependencies.get_exp_from_refresh_token] = _mock_get_exp_from_refresh_token
    app.dependency_overrides[authentication_dependencies.get_and_return_refresh_token] = (
        _mock_get_and_return_refresh_token
    )
    app.dependency_overrides[auth_dependencies.check_scopes] = _mock_check_scopes

    # Override public auth dependencies used by non-auth routers
    app.dependency_overrides[auth_dependencies.authenticate] = _mock_validate_access_token

    _override_credentials_and_db(app, password_hasher, token_manager, mock_db)

    return app


@pytest.fixture
def fast_api_client(fast_api_app: FastAPI) -> TestClient:
    """
    Creates and returns a TestClient instance for the given FastAPI application.

    Args:
        fast_api_app (FastAPI): The FastAPI application instance to test.

    Returns:
        TestClient: A test client for making requests to the FastAPI app during testing.
    """
    return TestClient(fast_api_app)


@pytest.fixture
def set_client_type_web(fast_api_app: FastAPI):
    """
    Sets the client type of the FastAPI application to "web".

    Args:
        fast_api_app (FastAPI): The FastAPI application instance.

    Returns:
        str: The client type that was set ("web").
    """
    fast_api_app.state._client_type = "web"
    return fast_api_app.state._client_type


@pytest.fixture
def set_client_type_mobile(fast_api_app: FastAPI):
    """
    Sets the client type of the given FastAPI application to "mobile".

    Args:
        fast_api_app (FastAPI): The FastAPI application instance whose client type is to be set.

    Returns:
        str: The value of the client type after setting it to "mobile".
    """
    fast_api_app.state._client_type = "mobile"
    return fast_api_app.state._client_type


@pytest.fixture
def fast_api_app_public(password_hasher, token_manager, mock_db) -> FastAPI:
    """
    Creates and configures a FastAPI application instance for testing public endpoints.

    This fixture is similar to fast_api_app but includes public routers that
    don't require authentication.

    Args:
        password_hasher: An object or callable used to hash passwords.
        token_manager: An object or callable responsible for managing authentication tokens.
        mock_db: A mock database session or connection.

    Returns:
        FastAPI: A configured FastAPI application instance for public endpoint testing.
    """
    app = FastAPI()

    _include_routers(app, _LEGACY_PUBLIC_ROUTERS)
    _override_credentials_and_db(app, password_hasher, token_manager, mock_db)

    return app


@pytest.fixture
def fast_api_client_public(fast_api_app_public: FastAPI) -> TestClient:
    """
    Creates and returns a TestClient instance for public endpoints.

    Args:
        fast_api_app_public (FastAPI): The FastAPI application instance configured
            for public endpoints.

    Returns:
        TestClient: A test client for making requests to public endpoints.
    """
    return TestClient(fast_api_app_public)
