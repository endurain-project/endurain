"""Public reverse-geocoding operations for activities."""

from sqlalchemy.orm import Session

import modules.activities.activity_geocoding.service as geocoding_service
import modules.activities.activity_geocoding.subscribers as geocoding_subscribers


def geocode_activity(activity_id: int, db: Session) -> bool:
    """Resolve and store an activity's location from its GPS stream."""
    return geocoding_service.geocode_and_store_activity_location(activity_id, db)


def backfill_missing_locations(db: Session) -> int:
    """Resolve locations for activities whose location is still missing."""
    return geocoding_service.backfill_missing_activity_locations(db)


def run_missing_location_backfill() -> None:
    """Run the locked scheduled location reconciliation pass."""
    geocoding_subscribers.run_missing_location_backfill()
