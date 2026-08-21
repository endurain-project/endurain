"""Process-local registry for installed activity package contributors."""

import modules.activities.contributors as activity_contributors

_activity_ingestion: dict[str, activity_contributors.ActivityIngestionContributor] = {}
_file_ingestion: dict[str, activity_contributors.FileIngestionContributor] = {}
_profile_activity: dict[str, activity_contributors.ProfileActivityContributor] = {}
_profile_global: dict[str, activity_contributors.ProfileGlobalContributor] = {}
_thumbnail_url_resolver: activity_contributors.ThumbnailUrlResolver | None = None


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


def register_thumbnail_url_resolver(resolver: activity_contributors.ThumbnailUrlResolver) -> None:
    """Install the resolver that turns a stored thumbnail key into a servable URL."""
    global _thumbnail_url_resolver
    _thumbnail_url_resolver = resolver


def resolve_thumbnail_url(key: str | None, activity_id: int) -> str | None:
    """Return the servable URL for an activity's stored thumbnail key.

    The seam that keeps the root ``activity`` package from importing
    ``activity_thumbnail``. Serializing an activity has to turn the stored key
    into a URL, and reaching for the thumbnail package to do it made the two
    import each other — the thumbnail subsystem derives its work *from* the
    activity row, so neither could be built, tested or extracted without the
    other. The root now states the question; whichever package can answer it
    registers itself at composition time.

    Args:
        key: The stored thumbnail key, or ``None``.
        activity_id: The owning activity, bound into the signed URL.

    Returns:
        The servable URL, or ``None`` when there is no key or no installed
        thumbnail subsystem to address it.
    """
    if _thumbnail_url_resolver is None:
        return None
    return _thumbnail_url_resolver(key, activity_id)


def clear() -> None:
    """Remove every installed contributor."""
    global _thumbnail_url_resolver
    _activity_ingestion.clear()
    _file_ingestion.clear()
    _profile_activity.clear()
    _profile_global.clear()
    _thumbnail_url_resolver = None
