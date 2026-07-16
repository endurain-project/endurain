"""Local fixtures for password_reset_tokens router tests."""

from unittest.mock import MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

import auth._internal.password_hasher as auth_password_hasher
import auth.password_reset_tokens.router as prt_router
import core.apprise as core_apprise
import core.database as core_database


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
    mock_email_svc = MagicMock(spec=core_apprise.AppriseService)
    hasher = auth_password_hasher.get_password_hasher()

    app.dependency_overrides[core_database.get_db] = lambda: mock_db
    app.dependency_overrides[core_apprise.get_email_service] = lambda: mock_email_svc
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
