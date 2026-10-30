"""Application-layer orchestration for activity laps.

Declares *what* an activity's laps are — the parent flag that hides them, the
two CRUD calls that read them and the fields the parent's other flags hide — and delegates *how* the paged read runs to the
shared :mod:`modules.activities.activity.child_collection_service` seam, which owns the
access gate and the rule that a refusal and an empty collection answer alike.

Reads are paginated. A lap count is not bounded by anything in the domain (a lap
per kilometre over an ultra, or a lap button pressed all day), so an unpaged
read would put no bound on the work or the payload one request could ask for.
"""

from sqlalchemy.orm import Session

import core.pagination as core_pagination
import modules.activities.activity.integration_service as activity_integration
import modules.activities.activity.schema as activity_schema
import modules.activities.activity_laps.crud as activity_laps_crud
import modules.activities.activity_laps.schema as activity_laps_schema

#: The lap fields each parent ``hide_*`` flag withholds from a non-owner, matching what the flag
#: clears on the activity itself. A lap repeats the activity's data, so serving it whole would
#: undo the flags the activity's own fields obey.
_FIELDS_BY_HIDE_FLAG: dict[str, tuple[str, ...]] = {
    "hide_start_time": ("start_time",),
    "hide_map": ("start_position_lat", "start_position_long", "end_position_lat", "end_position_long"),
    "hide_hr": ("avg_heart_rate", "max_heart_rate"),
    "hide_power": ("avg_power", "max_power", "normalized_power", "total_work"),
    "hide_cadence": (
        "avg_cadence",
        "max_cadence",
        "avg_fractional_cadence",
        "max_fractional_cadence",
        "total_cycles",
    ),
    "hide_speed": ("enhanced_avg_speed", "enhanced_max_speed"),
    "hide_pace": ("enhanced_avg_pace", "enhanced_max_pace"),
    "hide_elevation": ("total_ascent", "total_descent", "enhanced_min_altitude", "enhanced_max_altitude"),
}


_COLLECTION: activity_integration.ChildCollection[activity_laps_schema.ActivityLapsPage] = (
    activity_integration.ChildCollection(
        name="laps",
        hide_attr="hide_laps",
        fetch=activity_laps_crud.get_activity_laps,
        count=activity_laps_crud.count_activity_laps,
        build=activity_laps_schema.ActivityLapsPage.build,
        fields_by_hide_flag=_FIELDS_BY_HIDE_FLAG,
    )
)


def list_activity_laps(
    activity_id: int,
    requester_user_id: int,
    db: Session,
    *,
    page_number: int = 1,
    num_records: int = core_pagination.DEFAULT_CHILD_NUM_RECORDS,
) -> activity_laps_schema.ActivityLapsPage:
    """Return one page of an activity's laps for an authenticated caller.

    Args:
        activity_id: The parent activity.
        requester_user_id: The authenticated caller.
        db: Database session.
        page_number: 1-based page number.
        num_records: Page size.

    Returns:
        The page envelope. An empty page when the activity is not visible to the
        caller, its laps are hidden, or it has none — deliberately
        indistinguishable, so the endpoint cannot be used to probe which
        activities exist.
    """
    return _COLLECTION.list_for_requester(
        activity_id,
        requester_user_id,
        db,
        page_number=page_number,
        num_records=num_records,
    )


def list_public_activity_laps(
    activity_id: int,
    db: Session,
    *,
    page_number: int = 1,
    num_records: int = core_pagination.DEFAULT_CHILD_NUM_RECORDS,
) -> activity_laps_schema.ActivityLapsPage:
    """Return one page of a publicly shared activity's laps for an anonymous caller.

    Args:
        activity_id: The parent activity.
        db: Database session.
        page_number: 1-based page number.
        num_records: Page size.

    Returns:
        The page envelope, empty when the activity is not found, hidden, or not
        publicly visible.
    """
    return _COLLECTION.list_public(activity_id, db, page_number=page_number, num_records=num_records)


def list_for_activity(
    activity: activity_schema.ActivityRead,
    requester_user_id: int | None,
    db: Session,
) -> activity_laps_schema.ActivityLapsPage:
    """Return the first page of an activity's laps for a viewer who may already see the activity.

    Args:
        activity: The parent activity, as the viewer is allowed to see it.
        requester_user_id: The authenticated viewer, or ``None`` for an anonymous one.
        db: Database session.

    Returns:
        The page envelope, empty when the laps are hidden from this viewer.
    """
    return _COLLECTION.list_for_activity(
        activity,
        requester_user_id,
        db,
        page_number=1,
        num_records=core_pagination.DEFAULT_CHILD_NUM_RECORDS,
    )
