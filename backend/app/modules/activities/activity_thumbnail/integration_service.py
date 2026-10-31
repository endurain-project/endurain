"""Public addressing operations for activity thumbnails."""

import modules.activities.activity_thumbnail.signing as activity_thumbnail_signing


def thumbnail_url(key: str | None, activity_id: int) -> str | None:
    """Resolve a stored thumbnail key to a servable capability URL.

    Args:
        key: The stored thumbnail key, or None.
        activity_id: ID of the activity.

    Returns:
        The URL, or None when there is no thumbnail.
    """
    return activity_thumbnail_signing.thumbnail_url(key, activity_id)
