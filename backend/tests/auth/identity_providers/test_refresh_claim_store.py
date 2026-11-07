"""One refresh of an identity-provider token runs at a time, on any replica or worker."""

from unittest.mock import MagicMock

import jasil.providers as platform_providers
from jasil.backends.state_memory import MemoryState

import modules.auth.identity_providers.refresh_claim_store as refresh_claim_store


def _store(state=None) -> refresh_claim_store.IdpRefreshClaimStore:
    return refresh_claim_store.IdpRefreshClaimStore(state or MemoryState())


def test_a_session_is_claimed_once_until_released():
    store = _store()

    assert store.claim("session-1") is True
    assert store.claim("session-1") is False
    store.release("session-1")
    assert store.claim("session-1") is True


def test_each_session_has_its_own_claim():
    store = _store()

    assert store.claim("session-1") is True
    assert store.claim("session-2") is True


def test_an_unreachable_state_store_lets_the_refresh_run():
    """The compare-and-set write still guards the token, so a store outage must not stop every refresh."""
    state = MagicMock()
    state.set_if_absent.side_effect = platform_providers.StateBackendUnavailableError("down")
    state.delete.side_effect = platform_providers.StateBackendUnavailableError("down")
    store = _store(state)

    assert store.claim("session-1") is True
    store.release("session-1")
