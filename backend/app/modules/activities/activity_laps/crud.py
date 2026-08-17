"""Activity laps CRUD operations."""

from sqlalchemy import func, select
from sqlalchemy.orm import Session

import core.decorators as core_decorators
import core.logger as core_logger
import modules.activities.activity_laps.models as activity_laps_models
import modules.activities.activity_laps.schema as activity_laps_schema

logger = core_logger.get_logger(__name__)

_LAP_COLUMNS: tuple[str, ...] = (
    "start_time",
    "start_position_lat",
    "start_position_long",
    "end_position_lat",
    "end_position_long",
    "total_elapsed_time",
    "total_timer_time",
    "total_distance",
    "total_cycles",
    "total_calories",
    "avg_heart_rate",
    "max_heart_rate",
    "avg_cadence",
    "max_cadence",
    "avg_power",
    "max_power",
    "total_ascent",
    "total_descent",
    "intensity",
    "lap_trigger",
    "sport",
    "sub_sport",
    "normalized_power",
    "total_work",
    "avg_vertical_oscillation",
    "avg_stance_time",
    "avg_fractional_cadence",
    "max_fractional_cadence",
    "enhanced_avg_pace",
    "enhanced_avg_speed",
    "enhanced_max_pace",
    "enhanced_max_speed",
    "enhanced_min_altitude",
    "enhanced_max_altitude",
    "avg_vertical_ratio",
    "avg_step_length",
)


def _to_read_schema(
    orm_lap: activity_laps_models.ActivityLaps,
) -> activity_laps_schema.ActivityLapsRead:
    """
    Convert an ORM row to its Read schema.

    Args:
        orm_lap: The ORM model instance.

    Returns:
        A ActivityLapsRead schema instance.
    """
    return activity_laps_schema.ActivityLapsRead.model_validate(orm_lap)


@core_decorators.handle_db_errors
def get_activity_laps(
    activity_id: int,
    db: Session,
    *,
    page_number: int = 1,
    num_records: int = 200,
) -> list[activity_laps_schema.ActivityLapsRead]:
    """
    Retrieve one page of an activity's laps, in recorded order.

    Performs no access check: whether the caller may read these rows is decided
    by :mod:`modules.activities.activity_laps.service`.

    Args:
        activity_id: The activity ID.
        db: Database session.
        page_number: 1-based page number.
        num_records: Page size.

    Returns:
        The page of laps, empty when the activity has none.

    Raises:
        ProcessingError: If database error occurs.
    """
    stmt = (
        select(activity_laps_models.ActivityLaps)
        .where(activity_laps_models.ActivityLaps.activity_id == activity_id)
        # Ordered so paging is stable; the id is the insertion order the parser
        # produced, which is the order the laps were recorded in.
        .order_by(activity_laps_models.ActivityLaps.id)
        .offset((page_number - 1) * num_records)
        .limit(num_records)
    )
    activity_laps = db.scalars(stmt).all()

    return [_to_read_schema(lap) for lap in activity_laps]


@core_decorators.handle_db_errors
def count_activity_laps(activity_id: int, db: Session) -> int:
    """
    Count an activity's laps.

    Args:
        activity_id: The activity ID.
        db: Database session.

    Returns:
        The total number of laps.

    Raises:
        ProcessingError: If database error occurs.
    """
    stmt = select(func.count()).select_from(
        select(activity_laps_models.ActivityLaps.id)
        .where(activity_laps_models.ActivityLaps.activity_id == activity_id)
        .subquery()
    )
    return db.scalar(stmt) or 0


@core_decorators.handle_db_errors
def get_activities_laps(
    activity_ids: list[int],
    db: Session,
) -> list[activity_laps_schema.ActivityLapsRead]:
    """
    Retrieve the laps of several activities at once.

    Performs no access check and joins no parent row: which activities the
    caller may read is decided before this is reached, by the activities
    integration service that owns them.

    Args:
        activity_ids: The activities to read, already scoped to the caller.
        db: Database session.

    Returns:
        The laps of those activities, empty when there are none.

    Raises:
        ProcessingError: If database error occurs.
    """
    if not activity_ids:
        return []

    stmt = select(activity_laps_models.ActivityLaps).where(
        activity_laps_models.ActivityLaps.activity_id.in_(activity_ids)
    )
    return [_to_read_schema(row) for row in db.scalars(stmt).all()]


@core_decorators.handle_db_errors
def create_activity_laps(
    activity_laps: list[dict],
    activity_id: int,
    db: Session,
    *,
    commit: bool = True,
) -> None:
    """
    Bulk create activity laps for an activity.

    Args:
        activity_laps: List of lap dicts from
            file parsers.
        activity_id: The parent activity ID.
        db: Database session.

    Returns:
        None.

    Raises:
        ProcessingError: If database error occurs.
    """
    laps = [
        activity_laps_models.ActivityLaps(
            activity_id=activity_id,
            **{key: lap.get(key) for key in _LAP_COLUMNS},
        )
        for lap in activity_laps
    ]

    db.add_all(laps)
    # commit=False keeps the laps in the caller's open transaction (atomic ingestion).
    if commit:
        db.commit()
    else:
        db.flush()
