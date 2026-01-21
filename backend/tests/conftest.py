import os
import sys
from importlib import import_module
from pathlib import Path
from unittest.mock import MagicMock
from dotenv import load_dotenv

import pytest
from fastapi import Request, FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

# Load test environment variables from .env.test before importing app modules
env_test_path = Path(__file__).parent.parent / ".env.test"
load_dotenv(dotenv_path=env_test_path)

# Add the app directory to the Python path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "app"))

import users.users_sessions.router as users_session_router
import auth.password_hasher as auth_password_hasher
import auth.token_manager as auth_token_manager
import auth.security as auth_security
import users.users.schema as user_schema

# Variables and constants
DEFAULT_ROUTER_MODULES = [
    "session.router",
    "health.health_sleep.router",
    "health.health_steps.router",
    "health.health_targets.router",
    "health.health_weight.router",
    "users.users_goals.router",
]

PUBLIC_ROUTER_MODULES = [
    "server_settings.public_router",
]


@pytest.fixture
def password_hasher() -> auth_password_hasher.PasswordHasher:
    """
    Creates and returns an instance of auth_password_hasher.PasswordHasher using the get_password_hasher function.

    Returns:
        auth_password_hasher.PasswordHasher: An instance of the password hasher utility.
    """
    return auth_password_hasher.get_password_hasher()


@pytest.fixture
def token_manager() -> auth_token_manager.TokenManager:
    """
    Creates and returns a auth_token_manager.TokenManager instance configured with a test secret key.

    Returns:
        auth_token_manager.TokenManager: An instance of auth_token_manager.TokenManager initialized with a test secret key for use in testing.
    """
    return auth_token_manager.TokenManager(
        secret_key="test-secret-key-for-testing-only-min-32-chars"
    )


@pytest.fixture
def mock_db() -> MagicMock:
    """
    Creates and returns a MagicMock object that mimics the interface of a SQLAlchemy Session.

    Returns:
        MagicMock: A mock object with the specification of a SQLAlchemy Session.
    """
    return MagicMock(spec=Session)


@pytest.fixture
def sample_user_read() -> user_schema.UsersRead:
    """
    Creates and returns a sample instance of UsersRead for testing purposes.

    Returns:
        user_schema.UsersRead: A sample user object with predefined attributes.
    """
    return user_schema.UsersRead(
        id=1,
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
        user_schema.UsersRead: An instance representing an inactive user with predefined attributes.
    """
    return user_schema.UsersRead(
        id=2,
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
        Request: A MagicMock instance mimicking a Request object, with custom headers and client host set for testing purposes.
    """
    mock_req = MagicMock(spec=Request)
    mock_req.headers = {
        "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "X-Client-Type": "web",
    }
    mock_req.client = MagicMock()
    mock_req.client.host = "127.0.0.1"
    return mock_req


def _include_router_if_exists(app: FastAPI, dotted: str):
    """
    Attempts to import a module by its dotted path and include its 'router' attribute in the given FastAPI app if present.

    Args:
        app (FastAPI): The FastAPI application instance to which the router should be added.
        dotted (str): The dotted path of the module to import (e.g., 'myapp.api.v1.users').

    Notes:
        - If the module does not exist or does not have a 'router' attribute, the function silently ignores the error.
        - This is useful for conditionally including routers in a modular FastAPI project.
        - For health_weight router, adds /health_weight prefix to match expected test URLs
    """
    try:
        mod = import_module(dotted)
        router = getattr(mod, "router", None)
        if router is not None:
            if dotted == "health.health_sleep.router":
                app.include_router(router, prefix="/health_sleep")
            elif dotted == "health.health_steps.router":
                app.include_router(router, prefix="/health_steps")
            elif dotted == "health.health_targets.router":
                app.include_router(router, prefix="/health_targets")
            elif dotted == "health.health_weight.router":
                app.include_router(router, prefix="/health_weight")
            elif dotted == "users.users_goals.router":
                app.include_router(router, prefix="/user_goals")
            elif dotted == "server_settings.public_router":
                app.include_router(router, prefix="/server_settings/public")
            else:
                app.include_router(router)
    except Exception:
        # Silently ignore if module isn't present in this project
        pass


def _override_if_exists(app: FastAPI, dotted: str, attr: str, override_callable):
    """
    Overrides a FastAPI dependency if it exists in the specified module.

    Args:
        app (FastAPI): The FastAPI application instance where the dependency override will be applied.
        dotted (str): The dotted path to the module containing the dependency provider.
        attr (str): The attribute name of the dependency provider within the module.
        override_callable (Callable): The callable to use as the override for the dependency.

    Returns:
        Optional[Callable]: The original provider if it exists and was overridden, otherwise None.

    Notes:
        - If the module or attribute does not exist, or any exception occurs, the function silently fails and returns None.
    """
    try:
        mod = import_module(dotted)
        provider = getattr(mod, attr, None)
        if provider is not None:
            app.dependency_overrides[provider] = override_callable
            return provider
    except Exception:
        pass
    return None


@pytest.fixture
def fast_api_app(password_hasher, token_manager, mock_db) -> FastAPI:
    """
    Creates and configures a FastAPI application instance for testing purposes.
    This function sets up the FastAPI app with test-specific dependency overrides,
    including password hasher, token manager, and a mock database. It also injects
    a fake in-memory store for pending multi-factor authentication (MFA) attempts,
    and includes any default routers specified in the configuration.
        password_hasher: An object or callable used to hash passwords, typically a mock for testing.
        token_manager: An object or callable responsible for managing authentication tokens, typically a mock for testing.
        mock_db: A mock database session or connection to be used in place of the real database during tests.
        FastAPI: A configured FastAPI application instance with all test dependencies and routers included.
    """

    app = FastAPI()

    # Include any routers you have configured
    for dotted in DEFAULT_ROUTER_MODULES:
        _include_router_if_exists(app, dotted)

    # Include server_settings router with prefix
    _include_router_if_exists(app, "server_settings.router")
    try:
        mod = import_module("server_settings.router")
        router = getattr(mod, "router", None)
        if router is not None:
            app.include_router(router, prefix="/server_settings")
    except Exception:
        pass

    app.state._client_type = "web"

    def _client_type_override():
        return app.state._client_type

    class FakePendingMFAStore:
        """
        A fake in-memory store for tracking pending multi-factor authentication (MFA) login attempts.
        Primarily used for testing purposes to simulate the behavior of a pending MFA store.

        Attributes:
            calls (list): A list that records each call to add_pending_login as a tuple of (username, user_id).
            _store (dict): Internal storage mapping usernames to user IDs for pending logins.

        Methods:
            add_pending_login(username, user_id):
            get_pending_login(username):
            delete_pending_login(username):
            has_pending_login(username):
            clear_all():
        """

        def __init__(self):
            """
            Initializes the object and creates an empty list to store call records.
            """
            self.calls = []
            self._store = {}

        def add_pending_login(self, username, user_id):
            """
            Adds a pending login attempt to the internal calls list and store.

            Args:
                username (str): The username of the user attempting to log in.
                user_id (Any): The unique identifier of the user.

            Returns:
                None
            """
            self.calls.append((username, user_id))
            self._store[username] = user_id

        def get_pending_login(self, username: str):
            """
            Retrieve the pending login information for a given username.

            Args:
                username (str): The username to look up.

            Returns:
                Any: The pending login information associated with the username, or None if not found.
            """
            return self._store.get(username)

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

        def has_pending_login(self, username: str):
            """
            Checks if the given username has a pending login session.

            Args:
                username (str): The username to check for a pending login.

            Returns:
                bool: True if the username has a pending login, False otherwise.
            """
            return username in self._store

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
    app.state.mock_user_id = 1
    app.state.mock_session_id = "mock_session_id"

    # Security dependency overrides for testing authenticated endpoints
    def _mock_validate_access_token():
        """Mock validation that always passes"""
        return None

    def _mock_validate_refresh_token():
        """Mock validation that always passes"""
        return None

    def _mock_get_access_token():
        """Return mock access token"""
        return app.state.mock_access_token

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

    def _mock_get_and_return_access_token():
        """Return mock access token"""
        return app.state.mock_access_token

    def _mock_get_and_return_refresh_token():
        """Return mock refresh token"""
        return app.state.mock_refresh_token

    def _mock_check_scopes():
        """Mock scope check that always passes"""
        return None

    try:
        app.dependency_overrides[
            users_session_router.auth_security.header_client_type_scheme
        ] = _client_type_override
        app.dependency_overrides[
            users_session_router.users_session_schema.get_pending_mfa_store
        ] = lambda: fake_store

        # Override security dependencies for authenticated endpoint testing
        app.dependency_overrides[
            users_session_router.auth_security.validate_access_token
        ] = _mock_validate_access_token
        app.dependency_overrides[
            users_session_router.auth_security.validate_refresh_token
        ] = _mock_validate_refresh_token
        app.dependency_overrides[
            users_session_router.auth_security.get_access_token
        ] = _mock_get_access_token
        app.dependency_overrides[
            users_session_router.auth_security.get_refresh_token
        ] = _mock_get_refresh_token
        app.dependency_overrides[
            users_session_router.auth_security.get_sub_from_access_token
        ] = _mock_get_sub_from_access_token
        app.dependency_overrides[
            users_session_router.auth_security.get_sid_from_access_token
        ] = _mock_get_sid_from_access_token
        app.dependency_overrides[
            users_session_router.auth_security.get_sub_from_refresh_token
        ] = _mock_get_sub_from_refresh_token
        app.dependency_overrides[
            users_session_router.auth_security.get_sid_from_refresh_token
        ] = _mock_get_sid_from_refresh_token
        app.dependency_overrides[
            users_session_router.auth_security.get_and_return_access_token
        ] = _mock_get_and_return_access_token
        app.dependency_overrides[
            users_session_router.auth_security.get_and_return_refresh_token
        ] = _mock_get_and_return_refresh_token
        app.dependency_overrides[users_session_router.auth_security.check_scopes] = (
            _mock_check_scopes
        )
    except Exception:
        pass

    # Override auth_security for health_weight router
    try:
        app.dependency_overrides[auth_security.check_scopes] = _mock_check_scopes
        app.dependency_overrides[auth_security.get_sub_from_access_token] = (
            _mock_get_sub_from_access_token
        )
    except Exception:
        pass

    # Generic overrides
    _override_if_exists(
        app, "auth.password_hasher", "get_password_hasher", lambda: password_hasher
    )
    _override_if_exists(
        app,
        "session.auth_password_hasher",
        "get_password_hasher",
        lambda: password_hasher,
    )
    _override_if_exists(
        app, "auth.token_manager", "get_token_manager", lambda: token_manager
    )
    _override_if_exists(
        app, "session.auth_token_manager", "get_token_manager", lambda: token_manager
    )
    _override_if_exists(
        app, "core.database", "get_db", lambda: mock_db
    ) or _override_if_exists(
        app, "core_database", "get_db", lambda: mock_db
    ) or _override_if_exists(
        app, "app.core.database", "get_db", lambda: mock_db
    )

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

    # Include public routers
    for dotted in PUBLIC_ROUTER_MODULES:
        _include_router_if_exists(app, dotted)

    # Generic overrides
    _override_if_exists(
        app, "auth.password_hasher", "get_password_hasher", lambda: password_hasher
    )
    _override_if_exists(
        app, "auth.token_manager", "get_token_manager", lambda: token_manager
    )
    _override_if_exists(
        app, "core.database", "get_db", lambda: mock_db
    ) or _override_if_exists(
        app, "core_database", "get_db", lambda: mock_db
    ) or _override_if_exists(
        app, "app.core.database", "get_db", lambda: mock_db
    )

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
