"""A sign-in stack over SQLite: the real routes, the stores on the test platform and one user with a password."""

import uuid
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pyotp
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import core.cryptography as core_cryptography
import core.database as core_database
import core.exceptions as core_exceptions
import core.timezone as core_timezone
import modules.auth.account_security.public_router as password_change_router
import modules.auth.authentication.public_router as auth_router
import modules.auth.authentication.sso_public_router as exchange_router
import modules.auth.constants as auth_constants
import modules.auth.credentials.integration_service as credentials_integration
import modules.auth.identity_provider_links.integration_service as identity_provider_links_integration
import modules.auth.mfa.crud as mfa_crud
import modules.auth.mfa_backup_codes.crud as backup_codes_crud
import modules.auth.oauth_state.constants as oauth_state_constants
import modules.auth.oauth_state.integration_service as oauth_state_integration
import modules.auth.sessions.integration_service as sessions_integration
import modules.users.users.integration_service as users_integration
from tests._helpers.db import create_sqlite_session_factory, ensure_user

USER_ID = uuid.UUID(int=7)
USERNAME = f"user{USER_ID.hex}"
PASSWORD = "correct horse battery staple"
NEW_PASSWORD = "a brand new passphrase 42"
BACKUP_CODE = "ABCD-EFGH"
WEB = {"X-Client-Type": "web"}
MOBILE = {"X-Client-Type": "mobile"}
CHALLENGE = "E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM"
SSO_VERIFIER = "v" * 43
#: The S256 challenge of ``SSO_VERIFIER``.
SSO_CHALLENGE = "7w_YNF9DSfIdPf_pRjSq646_kPr-2-o9NAl16JGghdM"
SSO_IDP_ID = uuid.UUID(int=99)


def _build(session_policy, *, change_required: bool, mfa: bool):
    factory = create_sqlite_session_factory()
    ensure_user(factory, USER_ID)
    hasher = credentials_integration.get_password_hasher()
    with factory() as db:
        credentials_integration.set_local_password_hash(
            USER_ID, hasher.hash_password(PASSWORD), db, change_required=change_required
        )
        if mfa:
            mfa_crud.set_totp_factor(USER_ID, core_cryptography.encrypt_token_fernet(pyotp.random_base32()), db)
            backup_codes_crud.create_backup_codes(USER_ID, [hasher.hash_password(BACKUP_CODE)], db)
        db.commit()

    app = FastAPI()
    app.add_exception_handler(core_exceptions.DomainError, core_exceptions.domain_error_handler)
    app.include_router(auth_router.router, prefix="/auth")
    app.include_router(password_change_router.router, prefix="/auth")
    app.include_router(exchange_router.router, prefix="/auth")

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


@pytest.fixture
def mfa_plain_signin(session_policy):
    """The sign-in routes over SQLite for an account with MFA (one backup code) and a password it chose itself."""
    yield from _stack(session_policy, change_required=False, mfa=True)


@pytest.fixture
def aware_session_expiry():
    """Keep the absolute-timeout cap of a session claim out of the way: SQLite hands back naive creation times."""
    with patch("modules.auth.sessions.service._cap_expiry", side_effect=lambda expires_at, _created, _db: expires_at):
        yield


def create_sso_session(stack, client_type: auth_constants.ClientType = auth_constants.ClientType.WEB) -> uuid.UUID:
    """Create the session an identity-provider callback leaves for a client, stamped as the callback stamps it.

    Its PKCE challenge is the one of ``SSO_VERIFIER``. The account is linked to the provider, as for a sign-in whose
    subject was already linked, so the session's completion has nothing staged to apply.
    """
    session_id = uuid.uuid4()
    state_id, nonce = oauth_state_integration.create_state_id_and_nonce()
    with stack.factory() as db:
        if not identity_provider_links_integration.get_user_identity_provider_by_user_id_and_idp_id(
            USER_ID, SSO_IDP_ID, db
        ):
            identity_provider_links_integration.create_user_identity_provider(USER_ID, SSO_IDP_ID, "subject-1", db)
        state = oauth_state_integration.create_oauth_state(
            db=db,
            state_id=state_id,
            nonce=nonce,
            client_type=client_type.value,
            ip_address="127.0.0.1",
            idp_id=SSO_IDP_ID,
            code_challenge=SSO_CHALLENGE,
            code_challenge_method="S256",
            purpose=oauth_state_constants.OAuthStatePurpose.LOGIN,
            security_generation=0,
        )
        sessions_integration.create_session(
            session_id,
            users_integration.require_user(USER_ID, db),
            client_type,
            "127.0.0.1",
            "agent",
            None,
            core_timezone.to_utc_aware(state.expires_at),
            db,
            oauth_state_id=state_id,
            amr=[auth_constants.AuthMethod.FEDERATED],
            device_hash=None,
        )
        db.commit()
    return session_id
