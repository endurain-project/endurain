"""The activity operations exposed only to data migrations."""

from sqlalchemy.orm import Session

import modules.activities.activity.crud as activity_crud
import modules.activities.activity.schema as activity_schema

get_all_activities = activity_crud.get_all_activities
get_all_activities_for_migration = activity_crud.get_all_activities_for_migration
get_activity_by_id = activity_crud.get_activity_by_id
get_activities_with_legacy_thumbnail_path = activity_crud.get_activities_with_legacy_thumbnail_path


def edit_activity(
    user_id: int,
    activity_id: int,
    activity_attributes: activity_schema.ActivityEdit | activity_schema.ActivityRead,
    db: Session,
) -> activity_schema.ActivityRead:
    """Apply a historical activity edit and commit it, as migrations did.

    Args:
        user_id: Owner user ID.
        activity_id: ID of the activity to update.
        activity_attributes: The fields to apply.
        db: Database session.

    Returns:
        The updated activity.
    """
    activity = activity_crud.edit_activity(user_id, activity_id, activity_attributes, db)
    db.commit()
    return activity


def set_activity_thumbnail_key(activity_id: int, thumbnail_path: str | None, db: Session) -> None:
    """Set an activity's thumbnail path and commit it, as migrations did.

    Args:
        activity_id: Target activity ID.
        thumbnail_path: The path or storage key, or None to clear it.
        db: Database session.
    """
    activity_crud.set_activity_thumbnail_key(activity_id, thumbnail_path, db)
    db.commit()
