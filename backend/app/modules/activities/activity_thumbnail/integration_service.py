"""Public addressing and maintenance operations for activity thumbnails."""

import modules.activities.activity_thumbnail.service as thumbnail_service
import modules.activities.activity_thumbnail.signing as thumbnail_signing


def thumbnail_url(key: str | None, activity_id: int) -> str | None:
    """Resolve a stored thumbnail key to a servable capability URL."""
    return thumbnail_signing.thumbnail_url(key, activity_id)


def generate_missing_thumbnails() -> None:
    """Generate thumbnails for activities whose stored key is missing."""
    thumbnail_service.generate_missing_activity_thumbnails()


def regenerate_all_thumbnails() -> None:
    """Delete and regenerate every activity thumbnail."""
    thumbnail_service.delete_and_regenerate_all_activity_thumbnails()
