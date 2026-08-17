"""The seam that lets ingestion pull from a provider without importing one.

Ingestion needs "fetch this user's recent activities from everything they have
linked". Answering that by importing ``modules.strava`` and ``modules.garmin``
made the dependency mutual — both providers import back into
``activity.ingestion_service`` and ``activity_ingestion.bulk_entry`` — so neither
side could be built, tested or extracted without the other.

The direction is now one-way: a provider depends on activities and *registers*
itself here at startup; activities depends on nothing but this registry. Adding a
third provider means adding a module, not editing ingestion.

Registration happens once per process, from the composition root (``main`` for
the API, ``worker`` for the standalone job worker) — the same both-entrypoints
rule :mod:`~modules.activities.subscriber_registry` exists to enforce, and for
the same reason: the refresh job runs wherever it is claimed.
"""

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy.orm import Session

import core.logger as core_logger
import modules.activities.activity.schema as activities_schema

logger = core_logger.get_logger(__name__)

#: Fetch a user's activities recorded in ``[window_start, window_end]``, storing
#: each through the ingestion seam and returning what it stored. Returns an empty
#: list (or ``None``) when the user has not linked this provider — an unlinked
#: integration is not an error.
FetchWindow = Callable[
    [int, datetime, datetime, Session],
    Awaitable[list[activities_schema.Activity] | None],
]


@dataclass(frozen=True)
class ActivityProvider:
    """
    A third-party service ingestion can pull recent activities from.

    Attributes:
        name: Stable provider identifier, used for logging and de-duplication.
        fetch_window: Coroutine fetching one time window for one user.
    """

    name: str
    fetch_window: FetchWindow


_providers: dict[str, ActivityProvider] = {}


def register(provider: ActivityProvider) -> None:
    """
    Register a provider ingestion may pull from.

    Args:
        provider: The provider to register. Re-registering the same name
            replaces the previous entry, so a repeated call (a test, a second
            lifespan) is idempotent rather than duplicating the fetch.

    Returns:
        None.

    Raises:
        None.
    """
    _providers[provider.name] = provider


def registered() -> tuple[ActivityProvider, ...]:
    """
    Return every registered provider, in registration order.

    Args:
        None.

    Returns:
        The registered providers.

    Raises:
        None.
    """
    return tuple(_providers.values())


def clear() -> None:
    """
    Drop every registration.

    Args:
        None.

    Returns:
        None.

    Raises:
        None.
    """
    _providers.clear()
