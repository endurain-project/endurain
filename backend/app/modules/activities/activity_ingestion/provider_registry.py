"""The seam that lets ingestion pull from a provider without importing one.

Ingestion needs "fetch this user's recent activities from everything they have
linked". Importing ``modules.strava`` and ``modules.garmin`` to answer that would
make the dependency mutual, since both providers import back into ingestion.

The direction is one-way: a provider depends on activities and *registers*
itself here at startup; activities depends on nothing but this registry. Adding a
third provider means adding a module, not editing ingestion.

Registration happens once per process, from the composition root (``main`` for
the API, ``worker`` for the standalone job worker) — the same both-entrypoints
rule used for runtime module composition, and for the same reason: the refresh
job runs wherever it is claimed.
"""

from dataclasses import dataclass

import modules.activities.activity_ingestion.contracts as activity_ingestion_contracts


@dataclass(frozen=True)
class ActivityProvider:
    """A third-party service ingestion can pull recent activities from.

    Attributes:
        name: Stable provider identifier, used for logging and de-duplication.
        fetch_window: Fetches one time window for one user.
        linked_user_ids: Pages through the users who linked this provider.
    """

    name: str
    fetch_window: activity_ingestion_contracts.FetchWindow
    linked_user_ids: activity_ingestion_contracts.LinkedUserIds


_providers: dict[str, ActivityProvider] = {}
_bulk_formats: dict[str, activity_ingestion_contracts.BulkImportFormat] = {}


def register(provider: ActivityProvider) -> None:
    """Register a provider ingestion may pull from.

    Args:
        provider: The provider to register. Re-registering the same name
            replaces the previous entry, so a repeated call (a test, a second
            lifespan) is idempotent rather than duplicating the fetch.
    """
    _providers[provider.name] = provider


def registered() -> tuple[ActivityProvider, ...]:
    """Return every registered provider, in registration order.

    Returns:
        The registered providers.
    """
    return tuple(_providers.values())


def register_bulk_format(bulk_format: activity_ingestion_contracts.BulkImportFormat) -> None:
    """Register how a provider's bulk-import archive is laid out.

    Args:
        bulk_format: The format. Re-registering a name replaces the entry.
    """
    _bulk_formats[bulk_format.name] = bulk_format


def get_bulk_format(name: str) -> activity_ingestion_contracts.BulkImportFormat | None:
    """Return the bulk-import format registered under a name.

    Args:
        name: The format identifier.

    Returns:
        The format, or ``None`` when none is registered under that name.
    """
    return _bulk_formats.get(name)


def get(name: str) -> ActivityProvider | None:
    """Return the provider registered under a name.

    Args:
        name: The provider identifier.

    Returns:
        The provider, or ``None`` when none is registered under that name.
    """
    return _providers.get(name)


def clear() -> None:
    """Drop every registration."""
    _providers.clear()
    _bulk_formats.clear()
