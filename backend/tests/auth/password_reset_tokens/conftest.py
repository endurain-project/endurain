"""Local fixtures for password_reset_tokens router tests."""

from unittest.mock import MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from jasil.backends.state_memory import MemoryState
from sqlalchemy.orm import Session

import core.database as core_database
import core.dependencies as core_dependencies
import modules.auth.credentials.password_hasher as auth_password_hasher
import modules.auth.password_reset_tokens.public_router as prt_router


@pytest.fixture
def fast_api_app() -> FastAPI:
    """
    Create a minimal FastAPI app for password_reset_tokens
    router tests with all external dependencies overridden.

    Returns:
        FastAPI: Configured test application instance.
    """
    app = FastAPI()
    app.include_router(prt_router.router)

    mock_db = MagicMock(spec=Session)
    hasher = auth_password_hasher.get_password_hasher()

    app.dependency_overrides[core_database.get_db] = lambda: mock_db
    app.dependency_overrides[core_dependencies.get_platform_state] = lambda: MemoryState()
    app.dependency_overrides[auth_password_hasher.get_password_hasher] = lambda: hasher

    return app


@pytest.fixture
def fast_api_client(fast_api_app: FastAPI) -> TestClient:
    """
    Provide a TestClient for the password_reset_tokens test app.

    Args:
        fast_api_app: The configured test FastAPI application.

    Returns:
        TestClient: A test client for making HTTP requests.
    """
    return TestClient(fast_api_app)
