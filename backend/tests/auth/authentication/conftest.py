"""Sign-in against the production application: accounts arranged in committed sessions, driven over HTTP."""

import base64
import dataclasses
import hashlib
import uuid
from dataclasses import dataclass

import jasil.runtime as jasil_runtime
import pytest
import sqlalchemy as sa
from fastapi import FastAPI
from fastapi.testclient import TestClient
from httpx2 import Response
from jasil.events import Event
from jasil.providers import StateBackendUnavailableError
from sqlalchemy.orm import Session, sessionmaker

import core.config as core_config
import core.dependencies as core_dependencies
import modules.auth.credentials.integration_service as credentials_integration
import modules.auth.identity_providers.callback_service as callback_service
import modules.auth.identity_providers.contracts as identity_provider_contracts
import modules.auth.identity_providers.oidc_client_service as oidc_client_service
import modules.auth.identity_providers.staged_sign_in_store as staged_sign_in_store
import modules.auth.identity_providers.step_up_ticket_store as step_up_ticket_store
import modules.auth.identity_providers.token_service as idp_token_service
import modules.auth.mfa.pending_login_store as pending_login_store
import modules.auth.oauth_state.constants as oauth_state_constants
import modules.auth.oauth_state.integration_service as oauth_state_integration
import modules.auth.sessions.models as sessions_models
import modules.users.users.schema as users_schema
from tests._factories.identity_links import make_identity_link, make_identity_provider
from tests._factories.tokens import MfaFactors, make_mfa
from tests._factories.users import PASSWORD, make_user

NEW_PASSWORD = "A-brand-new-passphrase-42!"
WEB = {"X-Client-Type": "web"}
MOBILE = {"X-Client-Type": "mobile"}
VERIFIER = "v" * 43
#: The S256 challenge of ``VERIFIER``.
CHALLENGE = base64.urlsafe_b64encode(hashlib.sha256(VERIFIER.encode()).digest()).decode().rstrip("=")
PKCE = {"code_challenge": CHALLENGE, "code_challenge_method": "S256"}
WRONG_CODE = "000000"
LOGIN = f"{core_config.ROOT_PATH}/auth/login"
MFA_VERIFY = f"{core_config.ROOT_PATH}/auth/mfa/verify"
PASSWORD_CHANGE = f"{core_config.ROOT_PATH}/auth/password-change"
REFRESH = f"{core_config.ROOT_PATH}/auth/refresh"
LOGOUT = f"{core_config.ROOT_PATH}/auth/logout"


def exchange_path(session_id: object) -> str:
    """Return the path that exchanges a session for its tokens."""
    return f"{core_config.ROOT_PATH}/auth/sessions/{session_id}/tokens"


@dataclass(frozen=True)
class Account:
    """A user with a local password and, optionally, a second factor.

    Attributes:
        user: The committed user.
        password: The user's password.
        mfa: The enrolled second factors, or None.
    """

    user: users_schema.UserRead
    password: str
    mfa: MfaFactors | None = None

    @property
    def username(self) -> str:
        """The username that signs in."""
        return self.user.username

    @property
    def backup_code(self) -> str:
        """An unused backup code of the account."""
        assert self.mfa is not None
        return self.mfa.backup_codes[0]


def make_account(
    sessions: sessionmaker[Session], *, change_required: bool = False, mfa: bool = False, **fields: object
) -> Account:
    """Commit a user with a password, which an administrator may have set, and optionally enrol MFA.

    Args:
        sessions: The application's session factory.
        change_required: Whether the owner must choose a new password at the next sign-in.
        mfa: Whether the account has TOTP MFA with backup codes.
        **fields: Other user column values.
    """
    with sessions() as db:
        user = make_user(db, **fields)
        if change_required:
            credentials_integration.set_local_password_hash(
                user.id, credentials_integration.get_credential(user.id, db).password_hash, db, change_required=True
            )
        factors = make_mfa(db, user) if mfa else None
        db.commit()
    return Account(user, PASSWORD, factors)


@pytest.fixture
def account(committed_sessions) -> Account:
    """An account that chose its own password."""
    return make_account(committed_sessions)


@pytest.fixture
def must_change_account(committed_sessions) -> Account:
    """An account whose password an administrator set, so the owner must change it."""
    return make_account(committed_sessions, change_required=True)


@pytest.fixture
def mfa_account(committed_sessions) -> Account:
    """An account with MFA that chose its own password."""
    return make_account(committed_sessions, mfa=True)


@pytest.fixture
def mfa_must_change_account(committed_sessions) -> Account:
    """An account with MFA whose password an administrator set."""
    return make_account(committed_sessions, change_required=True, mfa=True)


def from_address(app: FastAPI, address: str) -> TestClient:
    """Return an anonymous client whose requests come from a client address."""
    return TestClient(app, client=(address, 50000))


def login(
    client: TestClient, account: Account, headers: dict[str, str] = WEB, *, pkce: bool = True, **fields: str
) -> Response:
    """Post the account's username and password to the login route; ``fields`` replace or add form fields.

    A mobile sign-in carries the PKCE challenge of ``VERIFIER`` unless ``pkce`` is false or ``fields`` name a
    PKCE field.
    """
    data = {"username": account.username, "password": account.password, **fields}
    if headers is MOBILE and pkce and not data.keys() & PKCE.keys():
        data |= PKCE
    return client.post(LOGIN, data=data, headers=headers)


def verify(client: TestClient, challenge: str, code: str, headers: dict[str, str] = WEB) -> Response:
    """Post an MFA code for a challenge."""
    return client.post(MFA_VERIFY, json={"mfa_challenge": challenge, "mfa_code": code}, headers=headers)


def exchange(client: TestClient, session_id: object, verifier: str = VERIFIER, headers: dict[str, str] = MOBILE):
    """Post a PKCE verifier to exchange a session for its tokens."""
    return client.post(exchange_path(session_id), json={"code_verifier": verifier}, headers=headers)


def session_count(sessions: sessionmaker[Session], user_id: uuid.UUID) -> int:
    """Count the user's session rows."""
    with sessions() as db:
        return db.scalar(
            sa.select(sa.func.count())
            .select_from(sessions_models.UsersSessions)
            .where(sessions_models.UsersSessions.user_id == user_id)
        )


def pending_mfa_store() -> pending_login_store.PendingMFALogin:
    """The platform's store of pending MFA sign-ins, as the routes read it."""
    return pending_login_store.PendingMFALogin(core_dependencies.get_platform_state())


def make_sso_session(
    sessions: sessionmaker[Session],
    user: users_schema.UserRead,
    *,
    client_type: str = "web",
    idp_id: uuid.UUID | None = None,
    staged: identity_provider_contracts.StagedSignIn | None = None,
    token_response: dict[str, object] | None = None,
) -> uuid.UUID:
    """Create the session an identity-provider callback leaves for a client, through the callback's own step.

    The user is linked to the provider unless ``idp_id`` names one the caller arranged. The OAuth state carries the
    PKCE challenge of ``VERIFIER`` and the account's current security generation.

    Args:
        sessions: The application's session factory.
        user: The user who signed in at the provider.
        client_type: The client type that started the sign-in.
        idp_id: The provider, or None for a new one the user is linked to.
        staged: What the sign-in applies to the account when it completes, or None.
        token_response: The provider's token response the session is stored with (for example its ``id_token``).

    Returns:
        The session's id.
    """
    state = core_dependencies.get_platform_state()
    oidc = oidc_client_service.OidcClientService(state, "test")
    service = callback_service.CallbackService(
        oidc,
        idp_token_service.IdpTokenService(oidc),
        step_up_ticket_store.StepUpTicketStore(state),
        staged_sign_in_store.StagedSignInStore(state),
        "https://app.example.com",
    )
    with sessions() as db:
        if idp_id is None:
            idp_id = make_identity_provider(db, f"provider-{uuid.uuid4().hex[:8]}")
            make_identity_link(db, user.id, idp_id, f"subject-{uuid.uuid4().hex[:8]}")
        state_id, nonce = oauth_state_integration.create_state_id_and_nonce()
        oauth_state_integration.create_oauth_state(
            state_id,
            nonce,
            client_type,
            "127.0.0.1",
            db,
            idp_id=idp_id,
            code_challenge=CHALLENGE,
            code_challenge_method="S256",
            purpose=oauth_state_constants.OAuthStatePurpose.LOGIN,
        )
        db.commit()
        oauth_state = oauth_state_integration.get_oauth_state_by_id_and_not_used(state_id, db)
        assert oauth_state is not None
        return service.create_callback_session(
            user, "127.0.0.1", "agent", oauth_state, idp_id, token_response or {}, db, idp_sid=None, staged=staged
        )


@pytest.fixture
def published():
    """Return a function that records the events of the given types the application publishes from now on."""

    def listen(*event_types: str) -> list[Event]:
        events: list[Event] = []
        bus = jasil_runtime.get_active_platform().events
        for event_type in event_types:
            bus.subscribe(event_type, events.append)
        return events

    return listen


class DownState:
    """A shared state whose every operation fails, as during an outage of its backend."""

    def __getattr__(self, name: str):
        def fail(*_args: object, **_kwargs: object):
            raise StateBackendUnavailableError("down")

        return fail


@pytest.fixture
def state_outage():
    """Return a function that makes the platform's shared state fail from then on, until the test ends."""

    def start() -> None:
        platform = jasil_runtime.get_active_platform()
        jasil_runtime.set_active_platform(dataclasses.replace(platform, state=DownState()))

    return start
