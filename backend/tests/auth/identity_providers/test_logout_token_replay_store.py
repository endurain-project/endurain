"""Tests for the single-use rule on accepted back-channel logout tokens."""

from unittest.mock import MagicMock

import pytest
from jasil.backends.state_memory import MemoryState
from jasil.providers import StateBackendUnavailableError

import core.exceptions as core_exceptions
import modules.auth.identity_providers.logout_token_replay_store as logout_token_replay_store


class TestClaimLogoutToken:
    def test_a_token_is_accepted_once(self):
        state = MemoryState()

        assert logout_token_replay_store.claim_logout_token(state, 3, "jti-1", 120) is True
        assert logout_token_replay_store.claim_logout_token(state, 3, "jti-1", 120) is False

    def test_providers_and_tokens_do_not_block_each_other(self):
        state = MemoryState()
        logout_token_replay_store.claim_logout_token(state, 3, "jti-1", 120)

        assert logout_token_replay_store.claim_logout_token(state, 3, "jti-2", 120) is True
        assert logout_token_replay_store.claim_logout_token(state, 4, "jti-1", 120) is True

    def test_the_jti_is_hashed_into_the_key_with_the_ttl_asked_for(self):
        state = MagicMock()
        state.set_if_absent.return_value = True

        logout_token_replay_store.claim_logout_token(state, 3, "jti:with/odd chars", 95)

        key, value, ttl = state.set_if_absent.call_args.args
        assert key.startswith("endurain:idp:logout-jti:3:")
        assert "jti" not in key.removeprefix("endurain:idp:logout-jti:3:")
        assert (value, ttl) == (b"1", 95)

    def test_an_unreachable_store_fails_closed_as_unavailable(self):
        state = MagicMock()
        state.set_if_absent.side_effect = StateBackendUnavailableError("down")

        with pytest.raises(core_exceptions.ServiceUnavailableError):
            logout_token_replay_store.claim_logout_token(state, 3, "jti-1", 120)


class TestReleaseLogoutToken:
    def test_a_released_token_can_be_claimed_again(self):
        state = MemoryState()
        logout_token_replay_store.claim_logout_token(state, 3, "jti-1", 120)

        logout_token_replay_store.release_logout_token(state, 3, "jti-1")

        assert logout_token_replay_store.claim_logout_token(state, 3, "jti-1", 120) is True

    def test_releasing_a_token_that_was_never_claimed_is_not_an_error(self):
        logout_token_replay_store.release_logout_token(MemoryState(), 3, "jti-1")

    def test_only_the_named_provider_and_token_are_released(self):
        state = MemoryState()
        logout_token_replay_store.claim_logout_token(state, 3, "jti-1", 120)
        logout_token_replay_store.claim_logout_token(state, 4, "jti-1", 120)

        logout_token_replay_store.release_logout_token(state, 3, "jti-1")

        assert logout_token_replay_store.claim_logout_token(state, 4, "jti-1", 120) is False

    def test_an_unreachable_store_is_unavailable(self):
        state = MagicMock()
        state.delete.side_effect = StateBackendUnavailableError("down")

        with pytest.raises(core_exceptions.ServiceUnavailableError):
            logout_token_replay_store.release_logout_token(state, 3, "jti-1")
