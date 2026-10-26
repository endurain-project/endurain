"""Local fixtures for profile router tests."""

from unittest.mock import MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from jasil.backends.state_memory import MemoryState
from sqlalchemy.orm import Session

import core.config as core_config
import core.database as core_database
import core.dependencies as core_dependencies
import core.exceptions as core_exceptions
import modules.auth.dependencies as auth_dependencies
import modules.auth.identity_providers.profile_router as auth_idp_profile_router
import modules.auth.identity_service as auth_identity_service
import modules.auth.mfa.profile_router as auth_mfa_profile_router
import modules.auth.mfa.setup_store as auth_mfa_setup_store
import modules.auth.sessions.profile_router as auth_sessions_profile_router
import modules.users.users_profile.browser_redirect_router as profile_browser_redirect_router
import modules.users.users_profile.dependencies as profile_dependencies
import modules.users.users_profile.export_state_store as profile_export_state_store
import modules.users.users_profile.import_state_store as profile_import_state_store
import modules.users.users_profile.router as profile_router


class FakeMFASecretStore:
    """In-memory MFA secret store for testing."""

    def __init__(self):
        self._store = {}

    def add_secret(self, user_id: int, secret: str) -> None:
        self._store[user_id] = secret

    def get_secret(self, user_id: int) -> str | None:
        return self._store.get(user_id)

    def delete_secret(self, user_id: int) -> None:
        self._store.pop(user_id, None)


@pytest.fixture
def local_mock_db() -> MagicMock:
    return MagicMock(spec=Session)


@pytest.fixture
def fake_mfa_secret_store() -> FakeMFASecretStore:
    return FakeMFASecretStore()


@pytest.fixture
def import_states() -> profile_import_state_store.ProfileImportStateStore:
    return profile_import_state_store.ProfileImportStateStore(MemoryState())


@pytest.fixture
def export_states() -> profile_export_state_store.ProfileExportStateStore:
    return profile_export_state_store.ProfileExportStateStore(MemoryState())


@pytest.fixture
def mock_identity_service() -> MagicMock:
    return MagicMock()


@pytest.fixture
def redirect_app(local_mock_db) -> FastAPI:
    app = FastAPI()

    app.include_router(
        profile_browser_redirect_router.router,
        prefix=core_config.ROOT_PATH + "/profile",
    )

    app.dependency_overrides[core_database.get_db] = lambda: local_mock_db

    return app


@pytest.fixture
def redirect_client(redirect_app: FastAPI) -> TestClient:
    return TestClient(redirect_app)


@pytest.fixture
def profile_app(
    local_mock_db,
    fake_mfa_secret_store,
    mock_identity_service,
    import_states,
    export_states,
) -> FastAPI:
    app = FastAPI()

    # The profile API is served by four routers: the profile's own, and auth's sessions, MFA and IdP links.
    app.include_router(
        profile_router.router,
        prefix=core_config.ROOT_PATH + "/profile",
    )
    app.include_router(auth_sessions_profile_router.router, prefix=core_config.ROOT_PATH + "/profile/sessions")
    app.include_router(auth_mfa_profile_router.router, prefix=core_config.ROOT_PATH + "/profile/mfa")
    app.include_router(auth_idp_profile_router.router, prefix=core_config.ROOT_PATH + "/profile/idp")

    core_exceptions.register_exception_handlers(app)

    app.dependency_overrides[core_database.get_db] = lambda: local_mock_db
    app.dependency_overrides[core_dependencies.get_storage] = lambda: MagicMock()
    app.dependency_overrides[auth_dependencies.get_sub_from_access_token] = lambda: 1
    app.dependency_overrides[auth_dependencies.get_sid_from_access_token] = lambda: "session-1"
    app.dependency_overrides[auth_dependencies.check_scopes] = lambda: None
    app.dependency_overrides[auth_identity_service.get_identity_service] = lambda: mock_identity_service
    app.dependency_overrides[auth_mfa_setup_store.get_mfa_secret_store] = lambda: fake_mfa_secret_store
    app.dependency_overrides[profile_dependencies.get_profile_import_state_store] = lambda: import_states
    app.dependency_overrides[profile_dependencies.get_profile_export_state_store] = lambda: export_states

    return app


@pytest.fixture
def profile_client(profile_app: FastAPI) -> TestClient:
    return TestClient(profile_app)
