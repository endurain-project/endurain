"""Tests for the OAuth-state secrets stored encrypted at rest."""

import pytest
import sqlalchemy as sa
from cryptography.fernet import Fernet

import modules.auth.oauth_state.constants as oauth_state_constants
import modules.auth.oauth_state.integration_service as oauth_state_integration
import modules.auth.oauth_state.models as oauth_state_models
from tests._helpers.db import create_sqlite_session

_NONCE = "n" * 43
_VERIFIER = "v" * 64


@pytest.fixture
def db(monkeypatch):
    monkeypatch.setenv("FERNET_KEY", Fernet.generate_key().decode())
    session = create_sqlite_session()
    yield session
    session.close()


def _create(db, state_id="s" * 43):
    return oauth_state_integration.create_oauth_state(
        state_id,
        _NONCE,
        "web",
        None,
        db,
        idp_code_verifier=_VERIFIER,
        purpose=oauth_state_constants.OAuthStatePurpose.LOGIN,
    )


def _stored(db):
    return db.execute(
        sa.select(oauth_state_models.OAuthState.nonce, oauth_state_models.OAuthState.idp_code_verifier)
    ).one()


def test_the_nonce_and_verifier_are_stored_encrypted(db):
    _create(db)

    nonce, verifier = _stored(db)
    assert nonce != _NONCE and verifier != _VERIFIER
    assert _NONCE not in nonce and _VERIFIER not in verifier


def test_the_created_state_carries_the_plaintext_secrets(db):
    state = _create(db)

    assert (state.nonce, state.idp_code_verifier) == (_NONCE, _VERIFIER)


def test_the_reads_return_the_plaintext_secrets(db):
    _create(db)

    for read in (
        oauth_state_integration.get_oauth_state_by_id_and_not_used,
        oauth_state_integration.get_oauth_state_by_id_not_expired,
    ):
        state = read("s" * 43, db)
        assert state is not None
        assert (state.nonce, state.idp_code_verifier) == (_NONCE, _VERIFIER)


def test_a_state_without_a_verifier_stores_none(db):
    oauth_state_integration.create_oauth_state(
        "t" * 43, _NONCE, "web", None, db, purpose=oauth_state_constants.OAuthStatePurpose.LOGIN
    )

    state = oauth_state_integration.get_oauth_state_by_id_not_expired("t" * 43, db)
    assert state is not None and state.idp_code_verifier is None
