"""One refresh of an identity-provider token runs at a time, on any replica or worker."""

import uuid
from unittest.mock import MagicMock

import jasil.providers as platform_providers
from jasil.backends.state_memory import MemoryState

import modules.auth.identity_providers.refresh_claim_store as refresh_claim_store

SESSION_ID = uuid.uuid4()
OTHER_SESSION_ID = uuid.uuid4()


def _store(state=None) -> refresh_claim_store.IdpRefreshClaimStore:
    return refresh_claim_store.IdpRefreshClaimStore(state or MemoryState())


def test_a_session_is_claimed_once_until_released():
    store = _store()

    assert store.claim(SESSION_ID) is True
    assert store.claim(SESSION_ID) is False
    store.release(SESSION_ID)
    assert store.claim(SESSION_ID) is True


def test_each_session_has_its_own_claim():
    store = _store()

    assert store.claim(SESSION_ID) is True
    assert store.claim(OTHER_SESSION_ID) is True


def test_an_unreachable_state_store_lets_the_refresh_run():
    """The compare-and-set write still guards the token, so a store outage must not stop every refresh."""
    state = MagicMock()
    state.set_if_absent.side_effect = platform_providers.StateBackendUnavailableError("down")
    state.delete.side_effect = platform_providers.StateBackendUnavailableError("down")
    store = _store(state)

    assert store.claim(SESSION_ID) is True
    store.release(SESSION_ID)
