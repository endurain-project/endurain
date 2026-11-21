"""Application-layer orchestration for activity laps.

Declares *what* an activity's laps are — the parent flag that hides them and the
two CRUD calls that read them — and delegates *how* the paged read runs to the
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

_COLLECTION: activity_integration.ChildCollection[activity_laps_schema.ActivityLapsPage] = (
    activity_integration.ChildCollection(
        name="laps",
        hide_attr="hide_laps",
        fetch=activity_laps_crud.get_activity_laps,
        count=activity_laps_crud.count_activity_laps,
        build=activity_laps_schema.ActivityLapsPage.build,
    )
)

_POSITION_FIELDS = ("start_position_lat", "start_position_long", "end_position_lat", "end_position_long")


def _without_positions(
    page: activity_laps_schema.ActivityLapsPage,
    activity: activity_schema.ActivityRead | None,
) -> activity_laps_schema.ActivityLapsPage:
    """Clear the lap positions of an activity that hides its route's start and end.

    The first lap starts and the last lap ends where the route does, so the
    positions would give away what the trimmed map hides.

    Args:
        page: A page of laps read for a non-owner.
        activity: The parent activity, or None when it is not visible.

    Returns:
        The page, with every lap position cleared when the parent hides them.
    """
    if activity is None or not activity.hide_start_end:
        return page
    items = [lap.model_copy(update=dict.fromkeys(_POSITION_FIELDS)) for lap in page.items]
    return page.model_copy(update={"items": items})


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
    page = _COLLECTION.list_for_requester(
        activity_id,
        requester_user_id,
        db,
        page_number=page_number,
        num_records=num_records,
    )
    if not page.items:
        return page
    activity = activity_integration.resolve_readable_parent(activity_id, requester_user_id, db)
    if activity is not None and activity.user_id == requester_user_id:
        return page
    return _without_positions(page, activity)


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
    page = _COLLECTION.list_public(activity_id, db, page_number=page_number, num_records=num_records)
    if not page.items:
        return page
    return _without_positions(page, activity_integration.resolve_public_parent(activity_id, db))
