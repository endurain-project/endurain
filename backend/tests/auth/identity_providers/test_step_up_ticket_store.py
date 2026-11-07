"""Tests for identity_providers.step_up_ticket_store."""

from unittest.mock import MagicMock

import pytest
from jasil.backends.state_memory import MemoryState
from jasil.providers import StateBackendUnavailableError

import core.attempt_state as core_attempt_state
import core.hashing as core_hashing
import modules.auth.identity_providers.constants as idp_constants
import modules.auth.identity_providers.contracts as idp_contracts
from modules.auth.identity_providers.step_up_ticket_store import StepUpTicketStore

_TICKET = idp_contracts.StepUpTicket(
    user_id=7, session_id="s" * 36, idp_id=3, code_challenge="c" * 43, action="api_key_create"
)


class TestStepUpTicketStore:
    def test_a_ticket_reads_back_what_was_issued(self):
        store = StepUpTicketStore(MemoryState())

        value = store.issue(_TICKET)

        assert store.read(value) == _TICKET

    def test_reading_does_not_redeem(self):
        store = StepUpTicketStore(MemoryState())
        value = store.issue(_TICKET)

        store.read(value)

        assert store.redeem(value) == _TICKET

    def test_a_ticket_is_redeemed_once(self):
        store = StepUpTicketStore(MemoryState())
        value = store.issue(_TICKET)

        assert store.redeem(value) == _TICKET
        assert store.redeem(value) is None
        assert store.read(value) is None

    def test_an_unknown_ticket_is_none(self):
        assert StepUpTicketStore(MemoryState()).read("unknown-ticket-value-that-was-never-issued-x") is None

    def test_the_state_holds_only_the_digest_of_the_ticket(self):
        state = MagicMock()
        state.set_if_absent.return_value = True

        value = StepUpTicketStore(state).issue(_TICKET)

        key = state.set_if_absent.call_args.args[0]
        assert value not in key
        assert core_hashing.sha256_hex(value) in key

    def test_a_ticket_expires_after_its_ttl(self):
        state = MagicMock()
        state.set_if_absent.return_value = True

        StepUpTicketStore(state).issue(_TICKET)

        assert state.set_if_absent.call_args.kwargs["ttl_seconds"] == idp_constants.STEP_UP_TICKET_TTL_SECONDS

    def test_a_malformed_stored_value_reads_as_absent(self):
        state = MagicMock()
        state.get.return_value = b"not json"

        assert StepUpTicketStore(state).read("x" * 43) is None

    @pytest.mark.parametrize("operation", ["issue", "read", "redeem"])
    def test_an_unreachable_state_store_fails_closed(self, operation):
        state = MagicMock()
        error = StateBackendUnavailableError("down")
        state.set_if_absent.side_effect = error
        state.get.side_effect = error
        state.get_and_delete.side_effect = error
        store = StepUpTicketStore(state)

        with pytest.raises(core_attempt_state.StateUnavailableError):
            if operation == "issue":
                store.issue(_TICKET)
            else:
                getattr(store, operation)("x" * 43)
