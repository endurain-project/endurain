"""What an SSO sign-in to an existing account applies at its completion is held encrypted, per session, for its
window."""

import logging
import uuid
from unittest.mock import MagicMock

import pytest
from jasil.backends.state_memory import MemoryState
from jasil.providers import StateBackendUnavailableError

import core.attempt_state as core_attempt_state
import core.hashing as core_hashing
import modules.auth.identity_providers.contracts as contracts
from modules.auth.identity_providers.staged_sign_in_store import StagedSignInStore
from tests._helpers.auth import MOCK_USER_ID

SESSION_ID = uuid.UUID("11111111-2222-3333-4444-555555555555")
IDP_ID = uuid.UUID(int=99)
STAGED = contracts.StagedSignIn(
    user_id=MOCK_USER_ID,
    idp_id=IDP_ID,
    subject="subject-secret-1",
    create_link=True,
    claims=contracts.SyncedClaims(name="Alice Example", email="alice@example.com", email_verified=True),
)
KEY = core_attempt_state.key("sso_sign_in", "staged", core_hashing.sha256_hex(str(SESSION_ID)))


def test_a_staged_sign_in_reads_back_until_it_is_discarded():
    store = StagedSignInStore(MemoryState())

    store.stage(SESSION_ID, STAGED, ttl_seconds=600)

    assert store.read(SESSION_ID) == STAGED
    assert store.read(SESSION_ID) == STAGED
    store.discard(SESSION_ID)
    assert store.read(SESSION_ID) is None


def test_another_session_finds_nothing():
    store = StagedSignInStore(MemoryState())
    store.stage(SESSION_ID, STAGED, ttl_seconds=600)

    assert store.read(uuid.uuid4()) is None


def test_the_record_is_stored_encrypted_under_the_digest_of_the_session_id_for_the_window_given():
    state = MagicMock()

    StagedSignInStore(state).stage(SESSION_ID, STAGED, ttl_seconds=123)

    key, payload = state.set.call_args.args
    assert key == KEY
    assert str(SESSION_ID) not in key
    assert state.set.call_args.kwargs == {"ttl_seconds": 123}
    for value in ("subject-secret-1", "alice@example.com", "Alice Example", str(MOCK_USER_ID)):
        assert value.encode() not in payload


def test_a_record_that_cannot_be_decrypted_reads_as_missing(caplog):
    state = MemoryState()
    state.set(KEY, b"not a fernet token", ttl_seconds=600)

    with caplog.at_level(logging.WARNING):
        assert StagedSignInStore(state).read(SESSION_ID) is None

    assert "could not be read" in caplog.text


@pytest.mark.parametrize("operation", ["stage", "read"])
def test_an_outage_fails_closed(operation):
    state = MagicMock()
    state.set.side_effect = StateBackendUnavailableError("down")
    state.get.side_effect = StateBackendUnavailableError("down")
    store = StagedSignInStore(state)

    with pytest.raises(core_attempt_state.StateUnavailableError):
        if operation == "stage":
            store.stage(SESSION_ID, STAGED, ttl_seconds=600)
        else:
            store.read(SESSION_ID)


def test_an_outage_while_discarding_leaves_the_record_to_expire(caplog):
    state = MagicMock()
    state.delete.side_effect = StateBackendUnavailableError("down")

    with caplog.at_level(logging.WARNING):
        StagedSignInStore(state).discard(SESSION_ID)

    state.delete.assert_called_once_with(KEY)
    assert "left to expire" in caplog.text
