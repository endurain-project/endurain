"""Registration surface for the authentication event subscribers."""

from jasil.providers import EventBusProvider

import modules.auth.authentication.subscribers as authentication_subscribers


def register_bus_subscribers(events: EventBusProvider) -> None:
    """Register the authentication bus subscribers."""
    authentication_subscribers.register_bus_subscribers(events)
