"""A provider's sign-in racing the edit that disables it, against real PostgreSQL rows."""

import uuid
from unittest.mock import MagicMock, patch

import pytest
from jasil.backends.state_memory import MemoryState
from sqlalchemy import text
from sqlalchemy.exc import OperationalError

import core.exceptions as core_exceptions
import modules.auth.identity_providers.callback_service as callback_service
import modules.auth.identity_providers.oidc_client_service as idp_oidc_client_service
import modules.auth.identity_providers.provider_service as idp_provider_service
import modules.auth.identity_providers.schema as idp_schema
import modules.auth.identity_providers.token_service as idp_token_service
import modules.auth.oauth_state.constants as oauth_state_constants
import modules.auth.oauth_state.integration_service as oauth_state_integration
import modules.auth.schema as auth_schema
import modules.users.users.integration_service as users_integration
from modules.auth.identity_providers import crud as idp_crud
from tests._helpers.auth import MOCK_USER_ID
from tests._helpers.db import ensure_user

STEP_UP = auth_schema.StepUpVerification()
VERIFIER = MagicMock()
_SESSION_POLICY_TARGET = "modules.server_settings.integration_service.get_session_policy"


def _oidc() -> idp_oidc_client_service.OidcClientService:
    return idp_oidc_client_service.OidcClientService(MemoryState(), "test")


def _service() -> callback_service.CallbackService:
    return callback_service.CallbackService(
        MagicMock(), idp_token_service.IdpTokenService(_oidc()), MagicMock(), "https://app"
    )


@pytest.fixture
def provider(pg_factory):
    """An enabled provider and a user, both stored."""
    ensure_user(pg_factory, MOCK_USER_ID)
    data = idp_schema.IdentityProviderCreate(
        name="Keycloak",
        slug="keycloak",
        issuer_url="https://idp.example.com",
        client_id="endurain",
        client_secret="secret",
        enabled=True,
    )
    with pg_factory() as db:
        state = idp_crud.create_identity_provider(data, db)
        db.commit()
        return state.id


def _set_enabled(factory, idp_id: uuid.UUID, enabled: bool, *, lock_timeout: str | None = None) -> None:
    with factory() as db:
        if lock_timeout:
            db.execute(text(f"SET lock_timeout = '{lock_timeout}'"))
        version = idp_crud.get_identity_provider(idp_id, db).version
        idp_provider_service.update_identity_provider(
            idp_id,
            idp_schema.IdentityProviderUpdate(name="Keycloak", slug="keycloak", enabled=enabled),
            STEP_UP,
            VERIFIER,
            _oidc(),
            db,
            if_match=f'"{version}"',
        )


def _sign_in(factory, idp_id: uuid.UUID, state_id: str, password_hasher, session_policy, *, db=None) -> uuid.UUID:
    """Run the callback's session creation for the user, in the given session or a new one."""

    def run(session):
        user = users_integration.require_user(MOCK_USER_ID, session)
        oauth_state_integration.create_oauth_state(
            state_id,
            "n" * 32,
            "web",
            "127.0.0.1",
            session,
            purpose=oauth_state_constants.OAuthStatePurpose.LOGIN,
        )
        state = oauth_state_integration.get_oauth_state_by_id_and_not_used(state_id, session)
        return _service().create_callback_session(
            user, "127.0.0.1", "agent", password_hasher, state, idp_id, {"access_token": "at"}, session, idp_sid=None
        )

    with patch(_SESSION_POLICY_TARGET, return_value=session_policy):
        if db is not None:
            return run(db)
        with factory() as session:
            return run(session)


def _live_sessions(factory) -> set[uuid.UUID]:
    with factory() as db:
        return set(db.execute(text("SELECT id FROM users_sessions")).scalars())


def test_a_callback_for_a_provider_disabled_meanwhile_creates_no_session(
    pg_factory, provider, password_hasher, session_policy
):
    _set_enabled(pg_factory, provider, False)

    with pytest.raises(core_exceptions.NotFoundError):
        _sign_in(pg_factory, provider, "a" * 32, password_hasher, session_policy)

    assert _live_sessions(pg_factory) == set()


def test_a_disable_waits_for_a_callback_holding_the_provider_and_then_ends_its_session(
    pg_factory, provider, password_hasher, session_policy
):
    with pg_factory() as callback:
        assert idp_crud.lock_provider_enabled(provider, callback) is True
        with pytest.raises(OperationalError):
            _set_enabled(pg_factory, provider, False, lock_timeout="200ms")
        session_id = _sign_in(pg_factory, provider, "b" * 32, password_hasher, session_policy, db=callback)

    assert _live_sessions(pg_factory) == {session_id}
    _set_enabled(pg_factory, provider, False)
    assert _live_sessions(pg_factory) == set()


def test_sessions_ended_by_a_disable_stay_gone_when_the_provider_is_enabled_again(
    pg_factory, provider, password_hasher, session_policy
):
    _sign_in(pg_factory, provider, "c" * 32, password_hasher, session_policy)
    _set_enabled(pg_factory, provider, False)
    assert _live_sessions(pg_factory) == set()

    _set_enabled(pg_factory, provider, True)

    assert _live_sessions(pg_factory) == set()
    new_session = _sign_in(pg_factory, provider, "d" * 32, password_hasher, session_policy)
    assert _live_sessions(pg_factory) == {new_session}
