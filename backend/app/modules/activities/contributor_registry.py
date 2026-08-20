"""Process-local registry for installed activity package contributors."""

import modules.activities.contributors as activity_contributors

_activity_ingestion: dict[str, activity_contributors.ActivityIngestionContributor] = {}
_file_ingestion: dict[str, activity_contributors.FileIngestionContributor] = {}
_profile_activity: dict[str, activity_contributors.ProfileActivityContributor] = {}
_profile_global: dict[str, activity_contributors.ProfileGlobalContributor] = {}


def register_activity_ingestion(contributor: activity_contributors.ActivityIngestionContributor) -> None:
    """Register or replace an activity-ingestion contributor by key."""
    _activity_ingestion[contributor.key] = contributor


def register_file_ingestion(contributor: activity_contributors.FileIngestionContributor) -> None:
    """Register or replace a file-ingestion contributor by key."""
    _file_ingestion[contributor.key] = contributor


def register_profile_activity(contributor: activity_contributors.ProfileActivityContributor) -> None:
    """Register or replace an activity-scoped profile contributor by key."""
    _profile_activity[contributor.key] = contributor


def register_profile_global(contributor: activity_contributors.ProfileGlobalContributor) -> None:
    """Register or replace a global profile contributor by key."""
    _profile_global[contributor.key] = contributor


def activity_ingestion_contributors() -> tuple[activity_contributors.ActivityIngestionContributor, ...]:
    """Return activity-ingestion contributors in registration order."""
    return tuple(_activity_ingestion.values())


def file_ingestion_contributors() -> tuple[activity_contributors.FileIngestionContributor, ...]:
    """Return file-ingestion contributors in registration order."""
    return tuple(_file_ingestion.values())


def profile_activity_contributors() -> tuple[activity_contributors.ProfileActivityContributor, ...]:
    """Return activity-scoped profile contributors in registration order."""
    return tuple(_profile_activity.values())


def profile_global_contributors() -> tuple[activity_contributors.ProfileGlobalContributor, ...]:
    """Return global profile contributors in registration order."""
    return tuple(_profile_global.values())


def get_activity_ingestion_contributor(
    key: str,
) -> activity_contributors.ActivityIngestionContributor | None:
    """Return the activity-ingestion contributor registered for a key."""
    return _activity_ingestion.get(key)


def get_file_ingestion_contributor(key: str) -> activity_contributors.FileIngestionContributor | None:
    """Return the file-ingestion contributor registered for a key."""
    return _file_ingestion.get(key)


def clear() -> None:
    """Remove every installed contributor."""
    _activity_ingestion.clear()
    _file_ingestion.clear()
    _profile_activity.clear()
    _profile_global.clear()
