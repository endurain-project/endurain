"""Application-layer orchestration for activity laps.

Sits between the thin route and :mod:`crud`, matching the layering the activities
core uses. It owns the access decision — delegated to the shared
:mod:`modules.activities.activity.child_access` gate — so ``crud`` is left with
nothing but persistence, and so "who may read an activity's laps?" is answered in
the layer a reviewer looks at rather than inline above a ``SELECT``.

Reads are paginated. A lap count is not bounded by anything in the domain (a lap
per kilometre over an ultra, or a lap button pressed all day), so the previous
"return every row" read had no ceiling on the work or the payload one request
could ask for.
"""

from sqlalchemy.orm import Session

import core.logger as core_logger
import core.pagination as core_pagination
import modules.activities.activity.child_access as activity_child_access
import modules.activities.activity_laps.crud as activity_laps_crud
import modules.activities.activity_laps.schema as activity_laps_schema

logger = core_logger.get_logger(__name__)

# The parent activity flag that hides laps from a non-owner.
_HIDE_ATTR = "hide_laps"


def _empty_page(page_number: int, num_records: int) -> activity_laps_schema.ActivityLapsPage:
    """Return an empty page — the answer to both "none" and "not allowed"."""
    return activity_laps_schema.ActivityLapsPage.build([], 0, page_number, num_records)


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
    if not activity_child_access.may_read_child(activity_id, requester_user_id, db, hide_attr=_HIDE_ATTR):
        return _empty_page(page_number, num_records)
    items = activity_laps_crud.get_activity_laps(activity_id, db, page_number=page_number, num_records=num_records)
    total = activity_laps_crud.count_activity_laps(activity_id, db)
    return activity_laps_schema.ActivityLapsPage.build(items, total, page_number, num_records)


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
    if not activity_child_access.may_read_public_child(activity_id, db, hide_attr=_HIDE_ATTR):
        return _empty_page(page_number, num_records)
    items = activity_laps_crud.get_activity_laps(activity_id, db, page_number=page_number, num_records=num_records)
    total = activity_laps_crud.count_activity_laps(activity_id, db)
    return activity_laps_schema.ActivityLapsPage.build(items, total, page_number, num_records)
