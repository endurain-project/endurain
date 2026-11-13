"""Single-use tickets that hand an identity-provider link from a native app to the system browser.

A native app starts a link with an authenticated request, but the callback requires the browser that follows the
provider URL to hold the binding cookie of the flow, and the system browser is not the app's HTTP client. The start
request therefore answers with a ticket instead: the browser redeems it once, receives the binding cookie and is sent
on to the provider. Tickets live in the platform ``StateProvider`` under the digest of their value, so they hold
across replicas and a dump of the state cannot be replayed.
"""

import secrets

from jasil.providers import StateBackendUnavailableError, StateProvider
from pydantic import ValidationError

import core.attempt_state as core_attempt_state
import core.hashing as core_hashing
import modules.auth.identity_providers.constants as idp_constants
import modules.auth.identity_providers.contracts as idp_contracts


def _ticket_key(ticket: str) -> str:
    """Build the storage key of a ticket from its digest.

    Args:
        ticket: The ticket value.

    Returns:
        The storage key.
    """
    return core_attempt_state.key("idp_link", "ticket", core_hashing.sha256_hex(ticket))


class LinkTicketStore:
    """Link tickets backed by the platform ``StateProvider``; every outage fails closed."""

    def __init__(self, state: StateProvider) -> None:
        """Initialize the store.

        Args:
            state: The platform state provider, resolved at the entry point.
        """
        self._state = state

    def issue(self, ticket: idp_contracts.LinkTicket) -> str:
        """Store a ticket and return its value.

        Args:
            ticket: What the redemption sets and redirects to.

        Returns:
            The opaque, URL-safe ticket value.

        Raises:
            StateUnavailableError: When the state store is unavailable.
        """
        payload = ticket.model_dump_json().encode()
        try:
            for _ in range(3):
                value = secrets.token_urlsafe(32)
                if self._state.set_if_absent(
                    _ticket_key(value), payload, ttl_seconds=idp_constants.LINK_TICKET_TTL_SECONDS
                ):
                    return value
        except StateBackendUnavailableError as err:
            core_attempt_state.raise_unavailable("issue_idp_link_ticket", err)
        raise RuntimeError("Failed to generate a unique link ticket after 3 attempts")  # pragma: no cover

    def redeem(self, value: str) -> idp_contracts.LinkTicket | None:
        """Remove a ticket atomically and return it, so it starts exactly one link.

        Args:
            value: The ticket value.

        Returns:
            The ticket, or ``None`` when it is unknown, expired, malformed or already redeemed.

        Raises:
            StateUnavailableError: When the state store is unavailable.
        """
        try:
            stored = self._state.get_and_delete(_ticket_key(value))
        except StateBackendUnavailableError as err:
            core_attempt_state.raise_unavailable("redeem_idp_link_ticket", err)
        if stored is None:
            return None
        try:
            return idp_contracts.LinkTicket.model_validate_json(stored)
        except ValidationError:
            return None
