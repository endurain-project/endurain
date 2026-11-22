"""Single-use tickets that carry a fresh identity-provider sign-in to the sensitive request it authorises.

The provider's callback issues a ticket; the request that needs the proof reads it, checks it against the
caller, and only then redeems it, so a request refused for another reason (a wrong MFA code) does not cost the
user another trip through the provider. Tickets live in the platform ``StateProvider`` under the digest of
their value, so they hold across replicas and a dump of the state cannot be replayed.
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
    return core_attempt_state.key("step_up", "ticket", core_hashing.sha256_hex(ticket))


def _decode(value: bytes | None) -> idp_contracts.StepUpTicket | None:
    """Read a stored ticket, treating a malformed one as absent.

    Args:
        value: The stored bytes, if any.

    Returns:
        The ticket, or ``None``.
    """
    if value is None:
        return None
    try:
        return idp_contracts.StepUpTicket.model_validate_json(value)
    except ValidationError:
        return None


class StepUpTicketStore:
    """Step-up tickets backed by the platform ``StateProvider``; every outage fails closed."""

    def __init__(self, state: StateProvider) -> None:
        """Initialize the store.

        Args:
            state: The platform state provider, resolved at the entry point.
        """
        self._state = state

    def issue(self, ticket: idp_contracts.StepUpTicket) -> str:
        """Store a ticket and return its value.

        Args:
            ticket: What the sign-in proved.

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
                    _ticket_key(value), payload, ttl_seconds=idp_constants.STEP_UP_TICKET_TTL_SECONDS
                ):
                    return value
        except StateBackendUnavailableError as err:
            core_attempt_state.raise_unavailable("issue_step_up_ticket", err)
        raise RuntimeError("Failed to generate a unique step-up ticket after 3 attempts")  # pragma: no cover

    def read(self, value: str) -> idp_contracts.StepUpTicket | None:
        """Return a ticket without redeeming it.

        Args:
            value: The ticket value.

        Returns:
            The ticket, or ``None`` when it is unknown, expired or already redeemed.

        Raises:
            StateUnavailableError: When the state store is unavailable.
        """
        try:
            return _decode(self._state.get(_ticket_key(value)))
        except StateBackendUnavailableError as err:
            core_attempt_state.raise_unavailable("read_step_up_ticket", err)

    def redeem(self, value: str) -> idp_contracts.StepUpTicket | None:
        """Remove a ticket atomically and return it, so it pays for exactly one request.

        Args:
            value: The ticket value.

        Returns:
            The ticket, or ``None`` when another request redeemed it first or it expired.

        Raises:
            StateUnavailableError: When the state store is unavailable.
        """
        try:
            return _decode(self._state.get_and_delete(_ticket_key(value)))
        except StateBackendUnavailableError as err:
            core_attempt_state.raise_unavailable("redeem_step_up_ticket", err)
