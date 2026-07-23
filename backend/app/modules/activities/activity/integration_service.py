"""The activities surface consumed by the provider/integration modules (Strava, Garmin).

A small, curated interface so the provider modules depend on a stable, intentional
set of activity operations instead of reaching into the full ``activity.crud`` (a
large ORM surface, most of it internal to the activities module). It is the
read/gear/delete counterpart to the ingestion seam: ingestion
(:mod:`~modules.activities.activity.ingestion_service` /
:mod:`~modules.activities.activity_ingestion.orchestrator`) is how a provider
*stores* a parsed activity; this is how a provider *looks up*, *re-gears*, and
*bulk-deletes* the activities it owns. Every function returns schemas/DTOs — no ORM
row crosses the boundary.

Enforced by the ``provider-activities-boundary`` import-linter contract:
``modules.strava`` / ``modules.garmin`` must not import ``activity.crud`` directly;
they go through this interface.
"""

from sqlalchemy.orm import Session

import modules.activities.activity.crud as activities_crud
import modules.activities.activity.schema as activities_schema


def get_activity_by_strava_id(
    strava_activity_id: int,
    user_id: int,
    db: Session,
) -> activities_schema.Activity | None:
    """Return the user's activity imported from the given Strava activity id.

    Args:
        strava_activity_id: The Strava provider activity id.
        user_id: The owning user id.
        db: Database session.

    Returns:
        The matching activity, or ``None`` when the user has no such import.
    """
    return activities_crud.get_activity_by_strava_id_from_user_id(strava_activity_id, user_id, db)


def get_activity_by_garminconnect_id(
    garminconnect_activity_id: int,
    user_id: int,
    db: Session,
) -> activities_schema.Activity | None:
    """Return the user's activity imported from the given Garmin Connect activity id.

    Args:
        garminconnect_activity_id: The Garmin Connect provider activity id.
        user_id: The owning user id.
        db: Database session.

    Returns:
        The matching activity, or ``None`` when the user has no such import.
    """
    return activities_crud.get_activity_by_garminconnect_id_from_user_id(garminconnect_activity_id, user_id, db)


def list_user_activities(user_id: int, db: Session) -> list[activities_schema.Activity] | None:
    """Return all of a user's activities (used by provider gear reconciliation).

    Args:
        user_id: The owning user id.
        db: Database session.

    Returns:
        The user's activities, or ``None`` when they have none.
    """
    return activities_crud.get_user_activities(user_id, db)


def list_user_activities_with_garminconnect_gear(
    user_id: int,
    db: Session,
) -> list[activities_schema.Activity] | None:
    """Return a user's activities that carry a Garmin Connect gear id.

    Args:
        user_id: The owning user id.
        db: Database session.

    Returns:
        The matching activities, or ``None`` when there are none.
    """
    return activities_crud.get_user_activities_by_user_id_and_garminconnect_gear_set(user_id, db)


def bulk_set_activities_gear(
    user_id: int,
    gear_assignments: dict[int, int | None],
    db: Session,
) -> int:
    """Assign gear to many of a user's activities at once.

    Args:
        user_id: The owning user id (ownership is enforced by the update).
        gear_assignments: Map of activity id -> gear id (or ``None`` to clear).
        db: Database session.

    Returns:
        The number of activities updated.
    """
    return activities_crud.bulk_set_activities_gear_id(user_id, gear_assignments, db)


def delete_all_strava_activities(user_id: int, db: Session) -> int:
    """Delete all of a user's Strava-sourced activities.

    Args:
        user_id: The owning user id.
        db: Database session.

    Returns:
        The number of activities deleted.
    """
    return activities_crud.delete_all_strava_activities_for_user(user_id, db)
