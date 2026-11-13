"""A first SSO token exchange clears the session's OAuth state, so a replay finds none and is answered 404."""

import base64
import hashlib
import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock, patch

import pytest

import core.exceptions as core_exceptions
import modules.auth.authentication.sso_exchange_service as sso_exchange_service
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
def pending_exchange(pg_factory, password_hasher, session_policy):
    """A web SSO-style session with its OAuth state, both stored in PostgreSQL."""
    ensure_user(pg_factory, _USER_ID)
    with (
        patch("modules.server_settings.integration_service.get_session_policy", return_value=session_policy),
        pg_factory() as db,
    ):
        user = users_integration.require_user(_USER_ID, db)
        oauth_state_integration.create_oauth_state(
            _STATE_ID,
            "n" * 32,
            "web",
            "127.0.0.1",
            db,
            code_challenge=_CHALLENGE,
            code_challenge_method="S256",
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
            password_hasher,
            datetime.now(UTC) + timedelta(days=1),
            db,
            oauth_state_id=_STATE_ID,
            amr=["fed"],
            device_hash=None,
        )
        db.commit()
    return pg_factory


def _exchange(factory, password_hasher, token_manager):
    with factory() as db:
        return sso_exchange_service.exchange_tokens_for_session(
            _SESSION_ID,
            _VERIFIER,
            None,
            "web",
            "127.0.0.1",
            "agent",
            MagicMock(),
            password_hasher,
            token_manager,
            db,
            device_id=None,
        )


def test_a_second_exchange_finds_the_state_the_first_one_cleared_and_answers_not_found(
    pending_exchange, password_hasher, token_manager, session_policy
):
    with patch("modules.server_settings.integration_service.get_session_policy", return_value=session_policy):
        first = _exchange(pending_exchange, password_hasher, token_manager)

        with pending_exchange() as db:
            session, state = sessions_integration.get_session_with_oauth_state(_SESSION_ID, db)
        assert first.body.session_id == _SESSION_ID
        assert state is None
        assert session.tokens_exchanged is True

        with pytest.raises(core_exceptions.NotFoundError) as replay:
            _exchange(pending_exchange, password_hasher, token_manager)
    assert replay.value.detail == _NOT_ELIGIBLE
