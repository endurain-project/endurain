"""A first SSO token exchange clears the session's OAuth state, so a replay finds none and is answered 404.

For an account with MFA the exchange only starts the MFA step, and the MFA step claims the session, once.
"""

import base64
import hashlib
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock, patch

import pytest
from jasil.backends.state_memory import MemoryState

import core.exceptions as core_exceptions
import modules.auth.authentication.schema as auth_schema
import modules.auth.authentication.service as authentication_service
import modules.auth.authentication.sso_exchange_service as sso_exchange_service
import modules.auth.identity_providers.crud as idp_crud
import modules.auth.identity_providers.schema as idp_schema
import modules.auth.mfa.pending_login_store as pending_login_store
import modules.auth.oauth_state.constants as oauth_state_constants
import modules.auth.oauth_state.integration_service as oauth_state_integration
import modules.auth.security_generation.integration_service as security_generation_integration
import modules.auth.sessions.integration_service as sessions_integration
import modules.users.users.integration_service as users_integration
from modules.auth.constants import ClientType
from tests._helpers.db import ensure_user

_USER_ID = uuid.UUID(int=7)
_SESSION_ID = uuid.UUID(int=9)
_STATE_ID = "a" * 32
_VERIFIER = "v" * 43
_CHALLENGE = base64.urlsafe_b64encode(hashlib.sha256(_VERIFIER.encode()).digest()).decode().rstrip("=")
_NOT_ELIGIBLE = "Session not found or not eligible for token exchange"


@pytest.fixture
def pending_exchange(pg_factory, session_policy):
    """A web identity-provider session with its OAuth state, both stored in PostgreSQL."""
    ensure_user(pg_factory, _USER_ID)
    with (
        patch("modules.server_settings.integration_service.get_session_policy", return_value=session_policy),
        pg_factory() as db,
    ):
        user = users_integration.require_user(_USER_ID, db)
        idp = idp_crud.create_identity_provider(
            idp_schema.IdentityProviderCreate(
                name="Keycloak",
                slug="keycloak",
                issuer_url="https://idp.example.com",
                client_id="endurain",
                client_secret="secret",
                enabled=True,
            ),
            db,
        )
        oauth_state_integration.create_oauth_state(
            _STATE_ID,
            "n" * 32,
            "web",
            "127.0.0.1",
            db,
            code_challenge=_CHALLENGE,
            code_challenge_method="S256",
            idp_id=idp.id,
            purpose=oauth_state_constants.OAuthStatePurpose.LOGIN,
            security_generation=security_generation_integration.current_generation(_USER_ID, db),
        )
        sessions_integration.create_session(
            _SESSION_ID,
            user,
            ClientType.WEB,
            "127.0.0.1",
            "agent",
            None,
            datetime.now(UTC) + timedelta(days=1),
            db,
            oauth_state_id=_STATE_ID,
            amr=["fed"],
            device_hash=None,
        )
        db.commit()
    return pg_factory


def _exchange(factory, token_manager, store=None):
    with factory() as db:
        return sso_exchange_service.exchange_tokens_for_session(
            _SESSION_ID,
            _VERIFIER,
            "web",
            "127.0.0.1",
            "agent",
            store or MagicMock(),
            token_manager,
            db,
            device_id=None,
        )


def _verify(factory, challenge, store, password_hasher, token_manager):
    with factory() as db:
        return authentication_service.verify_mfa_and_login(
            "127.0.0.1",
            "agent",
            auth_schema.MFALoginRequest(mfa_challenge=challenge, mfa_code="123456"),
            "web",
            MagicMock(),
            store,
            password_hasher,
            token_manager,
            db,
            password_change_store=MagicMock(),
            device_id=None,
        )


def test_a_second_exchange_finds_the_state_the_first_one_cleared_and_answers_not_found(
    pending_exchange, token_manager, session_policy
):
    with patch("modules.server_settings.integration_service.get_session_policy", return_value=session_policy):
        first = _exchange(pending_exchange, token_manager)

        with pending_exchange() as db:
            session, state = sessions_integration.get_session_with_oauth_state(_SESSION_ID, db)
        assert first.body.session_id == _SESSION_ID
        assert state is None
        assert session.tokens_exchanged is True

        with pytest.raises(core_exceptions.NotFoundError) as replay:
            _exchange(pending_exchange, token_manager)
    assert replay.value.detail == _NOT_ELIGIBLE


def test_the_mfa_step_claims_the_session_once_and_a_second_challenge_finds_it_used(
    pending_exchange, password_hasher, token_manager, session_policy
):
    store = pending_login_store.PendingMFALogin(MemoryState())
    with (
        patch("modules.server_settings.integration_service.get_session_policy", return_value=session_policy),
        patch("modules.auth.mfa.integration_service.is_mfa_enabled_for_user", return_value=True),
        patch("modules.auth.mfa.integration_service.get_sign_in_methods", return_value=["totp"]),
        patch("modules.auth.mfa.integration_service.verify_user_mfa", return_value=True),
    ):
        first = _exchange(pending_exchange, token_manager, store).body
        second = _exchange(pending_exchange, token_manager, store).body
        with pending_exchange() as db:
            session, state = sessions_integration.get_session_with_oauth_state(_SESSION_ID, db)
        assert (first.next_step, second.next_step) == ("mfa", "mfa")
        assert state is not None
        assert session.tokens_exchanged is False

        signed_in = _verify(pending_exchange, first.mfa_challenge, store, password_hasher, token_manager)

        with pending_exchange() as db:
            session, state = sessions_integration.get_session_with_oauth_state(_SESSION_ID, db)
        assert signed_in.body.session_id == _SESSION_ID
        assert state is None
        assert session.tokens_exchanged is True
        assert session.amr == ["fed", "otp", "mfa"]

        with pytest.raises(core_exceptions.SessionEndedError):
            _verify(pending_exchange, second.mfa_challenge, store, password_hasher, token_manager)
        with pytest.raises(core_exceptions.NotFoundError):
            _exchange(pending_exchange, token_manager, store)


def test_of_two_claims_of_one_session_only_the_first_commits(pending_exchange, session_policy):
    expiry = datetime.now(UTC) + timedelta(days=1)
    with (
        patch("modules.server_settings.integration_service.get_session_policy", return_value=session_policy),
        pending_exchange() as first,
        pending_exchange() as second,
    ):
        assert sessions_integration.claim_session_for_token_exchange(_SESSION_ID, "a", expiry, ["fed"], first)
        first.commit()
        assert sessions_integration.claim_session_for_token_exchange(_SESSION_ID, "b", expiry, ["fed"], second) is None


def test_two_concurrent_mfa_steps_for_one_session_sign_in_once(
    pending_exchange, password_hasher, token_manager, session_policy
):
    store = pending_login_store.PendingMFALogin(MemoryState())
    barrier = threading.Barrier(2)

    def verify(challenge):
        barrier.wait()
        try:
            return _verify(pending_exchange, challenge, store, password_hasher, token_manager)
        except core_exceptions.SessionEndedError as err:
            return err

    with (
        patch("modules.server_settings.integration_service.get_session_policy", return_value=session_policy),
        patch("modules.auth.mfa.integration_service.is_mfa_enabled_for_user", return_value=True),
        patch("modules.auth.mfa.integration_service.get_sign_in_methods", return_value=["totp"]),
        patch("modules.auth.mfa.integration_service.verify_user_mfa", return_value=True),
    ):
        challenges = [_exchange(pending_exchange, token_manager, store).body.mfa_challenge for _ in range(2)]
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(verify, challenges))

    assert sorted(type(result).__name__ for result in results) == ["AuthOutcome", "SessionEndedError"]
    with pending_exchange() as db:
        session, state = sessions_integration.get_session_with_oauth_state(_SESSION_ID, db)
    assert state is None
    assert session.tokens_exchanged is True
