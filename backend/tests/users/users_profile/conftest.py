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
import modules.auth.account_security.account_security_service as account_security_service
import modules.auth.account_security.identity_link_service as identity_link_service
import modules.auth.account_security.identity_links_router as auth_idp_profile_router
import modules.auth.account_security.integration_service as account_security_integration
import modules.auth.account_security.mfa_router as auth_mfa_profile_router
import modules.auth.account_security.mfa_workflow_service as mfa_workflow_service
import modules.auth.account_security.sessions_router as auth_sessions_profile_router
import modules.auth.credentials.integration_service as credentials_integration
import modules.auth.dependencies as auth_dependencies
import modules.auth.mfa.dependencies as auth_mfa_dependencies
import modules.users.users_profile.browser_redirect_router as profile_browser_redirect_router
import modules.users.users_profile.dependencies as profile_dependencies
import modules.users.users_profile.export_state_store as profile_export_state_store
import modules.users.users_profile.import_state_store as profile_import_state_store
import modules.users.users_profile.overview_router as profile_overview_router
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
def mock_auth_services() -> MagicMock:
    services = MagicMock()
    services.has_local_password.return_value = False
    return services


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
    mock_auth_services,
    import_states,
    export_states,
    monkeypatch,
) -> FastAPI:
    app = FastAPI()

    # The profile API is served by four routers: the profile's own, and auth's sessions, MFA and IdP links.
    app.include_router(
        profile_router.router,
        prefix=core_config.ROOT_PATH + "/profile",
    )
    app.include_router(profile_overview_router.router, prefix=core_config.ROOT_PATH + "/users")
    app.include_router(auth_sessions_profile_router.router, prefix=core_config.ROOT_PATH + "/profile/sessions")
    app.include_router(auth_mfa_profile_router.router, prefix=core_config.ROOT_PATH + "/profile/mfa")
    app.include_router(auth_idp_profile_router.router, prefix=core_config.ROOT_PATH + "/profile/identity-providers")

    core_exceptions.register_exception_handlers(app)

    app.dependency_overrides[core_database.get_db] = lambda: local_mock_db
    app.dependency_overrides[core_dependencies.get_storage] = lambda: MagicMock()
    app.dependency_overrides[auth_dependencies.get_sub_from_access_token] = lambda: 1
    app.dependency_overrides[auth_dependencies.get_sid_from_access_token] = lambda: "session-1"
    app.dependency_overrides[auth_dependencies.check_scopes] = lambda: None
    app.dependency_overrides[auth_mfa_dependencies.get_mfa_secret_store] = lambda: fake_mfa_secret_store
    app.dependency_overrides[profile_dependencies.get_profile_import_state_store] = lambda: import_states
    app.dependency_overrides[profile_dependencies.get_profile_export_state_store] = lambda: export_states

    monkeypatch.setattr(
        credentials_integration,
        "has_local_password",
        lambda user_id, db: mock_auth_services.has_local_password(user_id, db),
    )
    monkeypatch.setattr(
        account_security_integration,
        "verify_step_up",
        lambda step_up, user_id, session_id, action, store, db: mock_auth_services.verify_step_up(
            step_up, user_id, session_id, action, store
        ),
    )
    monkeypatch.setattr(
        account_security_integration,
        "change_own_password",
        lambda user_id, current_password, new_password, mfa_code, store, db, **kwargs: (
            mock_auth_services.change_own_password(
                user_id=user_id,
                current_password=current_password,
                new_password=new_password,
                mfa_code=mfa_code,
                step_up_store=store,
                **kwargs,
            )
        ),
    )
    monkeypatch.setattr(
        account_security_integration,
        "delete_other_user_sessions",
        lambda user_id, session_id, db: mock_auth_services.delete_other_user_sessions(user_id, session_id),
    )
    monkeypatch.setattr(
        account_security_integration,
        "get_mfa_status",
        lambda user_id, db: mock_auth_services.get_mfa_status(user_id),
    )
    monkeypatch.setattr(
        account_security_service,
        "list_user_sessions",
        lambda user_id, page, db: mock_auth_services.list_user_sessions(user_id, page),
    )
    monkeypatch.setattr(
        account_security_service,
        "delete_user_session",
        lambda session_id, user_id, db: mock_auth_services.delete_user_session(session_id, user_id),
    )
    monkeypatch.setattr(
        account_security_service,
        "delete_other_user_sessions",
        lambda user_id, session_id, db: mock_auth_services.delete_other_user_sessions(user_id, session_id),
    )
    monkeypatch.setattr(
        mfa_workflow_service,
        "get_mfa_status",
        lambda user_id, db: mock_auth_services.get_mfa_status(user_id),
    )
    monkeypatch.setattr(
        mfa_workflow_service,
        "get_backup_code_status",
        lambda user_id, db: mock_auth_services.get_backup_code_status(user_id),
    )
    monkeypatch.setattr(
        mfa_workflow_service,
        "setup_mfa",
        lambda user_id, store, db: mock_auth_services.setup_mfa(user_id, store),
    )
    monkeypatch.setattr(
        mfa_workflow_service,
        "enable_mfa",
        lambda request, user_id, session_id, step_up_store, secret_store, db: mock_auth_services.enable_mfa(
            request=request,
            user_id=user_id,
            session_id=session_id,
            step_up_store=step_up_store,
            mfa_secret_store=secret_store,
        ),
    )
    monkeypatch.setattr(
        mfa_workflow_service,
        "disable_mfa",
        lambda request, user_id, session_id, store, db: mock_auth_services.disable_mfa(
            request=request, user_id=user_id, session_id=session_id, step_up_store=store
        ),
    )
    monkeypatch.setattr(
        mfa_workflow_service,
        "verify_mfa",
        lambda request, user_id, store, db: mock_auth_services.verify_mfa(
            request=request, user_id=user_id, step_up_store=store
        ),
    )
    monkeypatch.setattr(
        mfa_workflow_service,
        "generate_backup_codes",
        lambda step_up, user_id, session_id, store, db: mock_auth_services.generate_backup_codes(
            step_up=step_up, user_id=user_id, session_id=session_id, step_up_store=store
        ),
    )
    monkeypatch.setattr(
        identity_link_service,
        "generate_link_token",
        lambda idp_id, request, http_request, user_id, session_id, store, db: mock_auth_services.generate_link_token(
            idp_id=idp_id,
            link_request=request,
            request=http_request,
            user_id=user_id,
            session_id=session_id,
            step_up_store=store,
        ),
    )
    monkeypatch.setattr(
        identity_link_service,
        "get_user_identity_provider_links",
        lambda user_id, db: mock_auth_services.get_user_identity_provider_links(user_id),
    )
    monkeypatch.setattr(
        identity_link_service,
        "delete_identity_provider_link",
        lambda idp_id, step_up, user_id, session_id, store, db: mock_auth_services.delete_identity_provider_link(
            idp_id=idp_id, step_up=step_up, user_id=user_id, session_id=session_id, step_up_store=store
        ),
    )

    return app


@pytest.fixture
def profile_client(profile_app: FastAPI) -> TestClient:
    return TestClient(profile_app)
