"""Concurrent completions of SSO sign-ins that each staged a link, against real PostgreSQL rows and row locks.

Two completions of one session: the session claim is one-shot, so only one applies the link. Two sessions that link
the same provider subject to different accounts: the unique key decides, and the loser signs in nobody.
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
from sqlalchemy import select

import core.exceptions as core_exceptions
import modules.auth.authentication.schema as auth_schema
import modules.auth.authentication.service as authentication_service
import modules.auth.authentication.sso_exchange_service as sso_exchange_service
import modules.auth.identity_provider_links.models as links_models
import modules.auth.identity_providers.contracts as idp_contracts
import modules.auth.identity_providers.crud as idp_crud
import modules.auth.identity_providers.event_publishers as idp_event_publishers
import modules.auth.identity_providers.schema as idp_schema
import modules.auth.mfa.pending_login_store as pending_login_store
import modules.auth.oauth_state.constants as oauth_state_constants
import modules.auth.oauth_state.integration_service as oauth_state_integration
import modules.auth.security_generation.integration_service as security_generation_integration
import modules.auth.sessions.integration_service as sessions_integration
import modules.users.users.integration_service as users_integration
from modules.auth.constants import ClientType
from modules.auth.identity_providers.staged_sign_in_store import StagedSignInStore
from tests._helpers.db import ensure_user

_FIRST_USER = uuid.UUID(int=21)
_SECOND_USER = uuid.UUID(int=22)
_SUBJECT = "subject-at-the-provider"
_VERIFIER = "v" * 43
_CHALLENGE = base64.urlsafe_b64encode(hashlib.sha256(_VERIFIER.encode()).digest()).decode().rstrip("=")


@pytest.fixture
def provider(pg_factory):
    """A provider that links by email, and two users, stored in PostgreSQL."""
    ensure_user(pg_factory, _FIRST_USER)
    ensure_user(pg_factory, _SECOND_USER)
    with pg_factory() as db:
        idp = idp_crud.create_identity_provider(
            idp_schema.IdentityProviderCreate(
                name="Keycloak",
                slug="keycloak",
                issuer_url="https://idp.example.com",
                client_id="endurain",
                client_secret="secret",
                enabled=True,
                link_by_email=True,
                sync_user_info=False,
                sync_email=False,
            ),
            db,
        )
        db.commit()
        return idp.id


def _staged_session(factory, state, idp_id: uuid.UUID, user_id: uuid.UUID) -> uuid.UUID:
    """Store the session an SSO callback creates for an email match, with the link it staged."""
    session_id = uuid.uuid4()
    state_id, nonce = oauth_state_integration.create_state_id_and_nonce()
    with factory() as db:
        oauth_state_integration.create_oauth_state(
            state_id,
            nonce,
            "web",
            "127.0.0.1",
            db,
            code_challenge=_CHALLENGE,
            code_challenge_method="S256",
            idp_id=idp_id,
            purpose=oauth_state_constants.OAuthStatePurpose.LOGIN,
            security_generation=security_generation_integration.current_generation(user_id, db),
        )
        sessions_integration.create_session(
            session_id,
            users_integration.require_user(user_id, db),
            ClientType.WEB,
            "127.0.0.1",
            "agent",
            None,
            datetime.now(UTC) + timedelta(minutes=10),
            db,
            oauth_state_id=state_id,
            amr=["fed"],
            device_hash=None,
        )
        db.commit()
    StagedSignInStore(state).stage(
        session_id,
        idp_contracts.StagedSignIn(
            user_id=user_id,
            idp_id=idp_id,
            subject=_SUBJECT,
            create_link=True,
            claims=idp_contracts.SyncedClaims(name=None, email=None, email_verified=False),
        ),
        ttl_seconds=600,
    )
    return session_id


def _exchange(factory, state, token_manager, session_id, store=None):
    with factory() as db:
        return sso_exchange_service.exchange_tokens_for_session(
            session_id,
            _VERIFIER,
            "web",
            "127.0.0.1",
            "agent",
            store or MagicMock(),
            token_manager,
            db,
            device_id=None,
            state=state,
        )


def _verify(factory, state, challenge, store, password_hasher, token_manager):
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
            state=state,
        )


def _links(factory) -> list[tuple[uuid.UUID, str]]:
    with factory() as db:
        rows = db.execute(select(links_models.IdentityLink.user_id, links_models.IdentityLink.idp_subject)).all()
        return [(row.user_id, row.idp_subject) for row in rows]


def _exchanged(factory, session_id) -> bool:
    with factory() as db:
        session, _ = sessions_integration.get_session_with_oauth_state(session_id, db)
        return session.tokens_exchanged


def test_two_sessions_linking_one_subject_to_two_accounts_sign_in_only_the_first_to_commit(
    pg_factory, provider, token_manager, session_policy
):
    state = MemoryState()
    with patch("modules.server_settings.integration_service.get_session_policy", return_value=session_policy):
        sessions = [_staged_session(pg_factory, state, provider, user) for user in (_FIRST_USER, _SECOND_USER)]
    barrier = threading.Barrier(2)

    def complete(session_id):
        barrier.wait()
        try:
            return _exchange(pg_factory, state, token_manager, session_id)
        except core_exceptions.NotFoundError as err:
            return err

    with (
        patch("modules.server_settings.integration_service.get_session_policy", return_value=session_policy),
        patch.object(idp_event_publishers, "publish_idp_linked") as linked,
        ThreadPoolExecutor(max_workers=2) as pool,
    ):
        results = list(pool.map(complete, sessions))

    assert sorted(type(result).__name__ for result in results) == ["AuthOutcome", "NotFoundError"]
    winner = 0 if isinstance(results[0], auth_schema.AuthOutcome) else 1
    winner_user = (_FIRST_USER, _SECOND_USER)[winner]
    assert _links(pg_factory) == [(winner_user, _SUBJECT)]
    assert _exchanged(pg_factory, sessions[winner]) is True
    assert _exchanged(pg_factory, sessions[1 - winner]) is False
    linked.assert_called_once()
    assert linked.call_args.args[0] == winner_user


def test_two_mfa_steps_for_one_session_apply_its_staged_link_once(
    pg_factory, provider, password_hasher, token_manager, session_policy
):
    state = MemoryState()
    with patch("modules.server_settings.integration_service.get_session_policy", return_value=session_policy):
        session_id = _staged_session(pg_factory, state, provider, _FIRST_USER)
    store = pending_login_store.PendingMFALogin(MemoryState())
    barrier = threading.Barrier(2)

    def verify(challenge):
        barrier.wait()
        try:
            return _verify(pg_factory, state, challenge, store, password_hasher, token_manager)
        except core_exceptions.SessionEndedError as err:
            return err

    with (
        patch("modules.server_settings.integration_service.get_session_policy", return_value=session_policy),
        patch("modules.auth.mfa.integration_service.is_mfa_enabled_for_user", return_value=True),
        patch("modules.auth.mfa.integration_service.get_sign_in_methods", return_value=["totp"]),
        patch("modules.auth.mfa.integration_service.verify_user_mfa", return_value=True),
        patch.object(idp_event_publishers, "publish_idp_linked") as linked,
    ):
        challenges = [
            _exchange(pg_factory, state, token_manager, session_id, store).body.mfa_challenge for _ in range(2)
        ]
        assert _links(pg_factory) == []
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(verify, challenges))

    assert sorted(type(result).__name__ for result in results) == ["AuthOutcome", "SessionEndedError"]
    assert _links(pg_factory) == [(_FIRST_USER, _SUBJECT)]
    assert _exchanged(pg_factory, session_id) is True
    linked.assert_called_once()
    assert StagedSignInStore(state).read(session_id) is None
