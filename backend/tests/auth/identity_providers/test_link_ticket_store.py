"""Tests for identity_providers.link_ticket_store: the single-use ticket that hands a link to the system browser."""

from unittest.mock import MagicMock

import pytest
from jasil.backends.state_memory import MemoryState
from jasil.providers import StateBackendUnavailableError

import core.attempt_state as core_attempt_state
import core.hashing as core_hashing
import modules.auth.identity_providers.constants as idp_constants
import modules.auth.identity_providers.contracts as idp_contracts
from modules.auth.identity_providers.link_ticket_store import LinkTicketStore

_TICKET = idp_contracts.LinkTicket(
    authorization_url="https://idp.example.com/authorize?state=s", browser_binding="b" * 43
)


class TestLinkTicketStore:
    def test_a_ticket_redeems_to_what_was_issued(self):
        store = LinkTicketStore(MemoryState())

        value = store.issue(_TICKET)

        assert store.redeem(value) == _TICKET

    def test_a_ticket_pays_for_one_redemption(self):
        store = LinkTicketStore(MemoryState())
        value = store.issue(_TICKET)

        assert store.redeem(value) is not None
        assert store.redeem(value) is None

    def test_an_unknown_ticket_redeems_to_nothing(self):
        assert LinkTicketStore(MemoryState()).redeem("unknown") is None

    def test_tickets_are_distinct_and_url_safe(self):
        store = LinkTicketStore(MemoryState())

        first, second = store.issue(_TICKET), store.issue(_TICKET)

        assert first != second
        assert len(first) >= 43
        assert all(character.isalnum() or character in "-_" for character in first)

    def test_the_state_holds_the_digest_of_the_ticket_and_expires_it(self):
        state = MagicMock()
        state.set_if_absent.return_value = True

        value = LinkTicketStore(state).issue(_TICKET)

        key = core_attempt_state.key("idp_link", "ticket", core_hashing.sha256_hex(value))
        assert state.set_if_absent.call_args.args[0] == key
        assert value not in key
        assert state.set_if_absent.call_args.kwargs["ttl_seconds"] == idp_constants.LINK_TICKET_TTL_SECONDS

    def test_a_malformed_stored_ticket_redeems_to_nothing(self):
        state = MagicMock()
        state.get_and_delete.return_value = b"not json"

        assert LinkTicketStore(state).redeem("t") is None

    def test_a_state_outage_fails_closed(self):
        state = MagicMock()
        state.set_if_absent.side_effect = StateBackendUnavailableError("down")
        state.get_and_delete.side_effect = StateBackendUnavailableError("down")
        store = LinkTicketStore(state)

        with pytest.raises(core_attempt_state.StateUnavailableError):
            store.issue(_TICKET)
        with pytest.raises(core_attempt_state.StateUnavailableError):
            store.redeem("t")
