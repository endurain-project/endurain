"""A sign-in stack over SQLite: the real routes, the stores on the test platform and one user with a password."""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pyotp
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import core.cryptography as core_cryptography
import core.database as core_database
import core.exceptions as core_exceptions
import modules.auth.account_security.public_router as password_change_router
import modules.auth.authentication.public_router as auth_router
import modules.auth.credentials.integration_service as credentials_integration
import modules.auth.mfa.crud as mfa_crud
import modules.auth.mfa_backup_codes.crud as backup_codes_crud
from tests._helpers.db import create_sqlite_session_factory, ensure_user

USER_ID = 7
USERNAME = "user7"
PASSWORD = "correct horse battery staple"
NEW_PASSWORD = "a brand new passphrase 42"
BACKUP_CODE = "ABCD-EFGH"
WEB = {"X-Client-Type": "web"}
MOBILE = {"X-Client-Type": "mobile"}
CHALLENGE = "E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM"


def _build(session_policy, *, change_required: bool, mfa: bool):
    factory = create_sqlite_session_factory()
    ensure_user(factory, USER_ID)
    hasher = credentials_integration.get_password_hasher()
    with factory() as db:
        credentials_integration.set_local_password_hash(
            USER_ID, hasher.hash_password(PASSWORD), db, change_required=change_required
        )
        if mfa:
            mfa_crud.update_user_mfa(
                USER_ID, db, encrypted_secret=core_cryptography.encrypt_token_fernet(pyotp.random_base32())
            )
            backup_codes_crud.create_backup_codes(USER_ID, [hasher.hash_password(BACKUP_CODE)], db)
        db.commit()

    app = FastAPI()
    app.add_exception_handler(core_exceptions.DomainError, core_exceptions.domain_error_handler)
    app.include_router(auth_router.router, prefix="/auth")
    app.include_router(password_change_router.router, prefix="/auth")

    def get_db():
        db = factory()
        try:
            yield db
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

    app.dependency_overrides[core_database.get_db] = get_db
    return app, factory


def _stack(session_policy, *, change_required: bool, mfa: bool):
    app, factory = _build(session_policy, change_required=change_required, mfa=mfa)
    settings = MagicMock(local_login_enabled=True, password_length_regular_users=12, password_length_admin_users=12)
    with (
        patch("modules.server_settings.integration_service.get_session_policy", return_value=session_policy),
        patch("modules.server_settings.integration_service.get_server_settings", return_value=settings),
    ):
        yield SimpleNamespace(client=TestClient(app), app=app, factory=factory)
    factory.kw["bind"].dispose()


@pytest.fixture
def signin(session_policy):
    """The sign-in routes over SQLite for an account whose password an administrator set (must be changed)."""
    yield from _stack(session_policy, change_required=True, mfa=False)


@pytest.fixture
def plain_signin(session_policy):
    """The sign-in routes over SQLite for an account that chose its own password."""
    yield from _stack(session_policy, change_required=False, mfa=False)


@pytest.fixture
def mfa_signin(session_policy):
    """The sign-in routes over SQLite for an account with MFA (one backup code) and a must-change password."""
    yield from _stack(session_policy, change_required=True, mfa=True)
