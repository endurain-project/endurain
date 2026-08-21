"""CRUD operations for activities."""

from collections import defaultdict
from collections.abc import Sequence
from datetime import UTC, date, datetime
from typing import Any, cast

from pydantic import BaseModel
from sqlalchemy import (
    CursorResult,
    and_,
    case,
    desc,
    func,
    literal,
    or_,
    select,
    tuple_,
)
from sqlalchemy import (
    delete as sa_delete,
)
from sqlalchemy import (
    update as sa_update,
)
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

import core.decorators as core_decorators
import core.exceptions as core_exceptions
import core.logger as core_logger
import core.sanitization as core_sanitization
import core.timezone as core_timezone
import modules.activities.activity.constants as activities_constants
import modules.activities.activity.contracts as activities_contracts
import modules.activities.activity.models as activities_models
import modules.activities.activity.query as activities_query
import modules.activities.activity.schema as activities_schema
import modules.activities.activity.serializers as activities_serializers

logger = core_logger.get_logger(__name__)

# Frontend sort keys resolved to their model columns. Derived from the single
# vocabulary in ``constants`` rather than restated, so a key the transport layer
# accepts always has an ordering here.
SORT_MAP: dict[str, tuple[Any, ...]] = {
    key: tuple(getattr(activities_models.Activity, name) for name in column_names)
    for key, column_names in activities_constants.ACTIVITY_SORT_FIELDS.items()
}

_DEFAULT_SORT_COLUMNS = SORT_MAP[activities_constants.DEFAULT_ACTIVITY_SORT_FIELD]

# Sorts below every real value, so NULLs land last.
_NULL_SORT_SENTINEL = -999999

# Columns that need COALESCE-with-sentinel so NULLs sort last
_NUMERIC_SORT_COLUMNS = {
    activities_models.Activity.distance,
    activities_models.Activity.total_timer_time,
    activities_models.Activity.calories,
    activities_models.Activity.elevation_gain,
    activities_models.Activity.pace,
    activities_models.Activity.average_hr,
}

# Text columns coalesced to "" so an unset place name orders with the empty ones
# instead of wherever the backend happens to put NULL.
_TEXT_SORT_COLUMNS = {
    activities_models.Activity.country,
    activities_models.Activity.city,
    activities_models.Activity.town,
}


def _sort_order_by(sort_by: str | None, sort_order: str | None) -> list[Any]:
    """Build the ORDER BY clauses for an activity list request.

    Args:
        sort_by: The requested sort key, already validated by the transport layer.
        sort_order: ``asc`` or ``desc``; anything else orders descending.

    Returns:
        One clause per column the key orders by, highest precedence first.
    """
    ascending = bool(sort_order and sort_order.lower() == "asc")
    columns = SORT_MAP.get(sort_by or "", _DEFAULT_SORT_COLUMNS)
    clauses = []
    for column in columns:
        if column in _NUMERIC_SORT_COLUMNS:
            ordered = func.coalesce(column, _NULL_SORT_SENTINEL)
        elif column in _TEXT_SORT_COLUMNS:
            ordered = func.coalesce(column, "")
        else:
            ordered = column
        clauses.append(ordered.asc() if ascending else ordered.desc())
    return clauses


def _is_not_live_strava_api_activity():
    """Return the policy predicate excluding live Strava API data."""
    return activities_models.Activity.strava_activity_id.is_(None)


def _visible_to_requester_condition(followee_ids: Sequence[int] | None):
    """Build the non-owner activity visibility condition.

    Live Strava API data is owner-only under the Strava API Policy, regardless
    of the activity's Endurain visibility. A Strava bulk-export file uploaded by
    the user does not populate ``strava_activity_id`` and remains governed by
    the normal visibility rules.

    Takes the requester's accepted followees already resolved, rather than a
    user id plus a session: answering "who does this person follow?" is a
    question for another bounded context, and a ``SELECT`` that has to ask it
    first is a service decision wearing a persistence layer's clothes.

    Args:
        followee_ids: The requester's accepted-followee user ids, or ``None``
            for an anonymous/public-only read.

    Returns:
        SQLAlchemy condition limiting rows to public or accepted
        follower-visible activities.
    """
    visibility_conditions = [activities_models.Activity.visibility == 0]
    if followee_ids:
        visibility_conditions.append(
            and_(
                activities_models.Activity.visibility == 1,
                activities_models.Activity.user_id.in_(followee_ids),
            )
        )

    return and_(
        activities_models.Activity.is_hidden.is_(False),
        _is_not_live_strava_api_activity(),
        or_(*visibility_conditions),
    )


def _apply_activity_visibility_filter(
    stmt,
    *,
    user_is_owner: bool,
    followee_ids: Sequence[int] | None,
):
    """Apply non-owner visibility filtering to an activity query.

    Args:
        stmt: SQLAlchemy select statement.
        user_is_owner: Whether the requester owns all candidate
            rows.
        followee_ids: The requester's accepted-followee user ids, resolved by
            the caller.

    Returns:
        The original statement for owner reads, otherwise a
        filtered statement.
    """
    if user_is_owner:
        return stmt
    return stmt.where(_visible_to_requester_condition(followee_ids))


@core_decorators.handle_db_errors
def get_all_activities(
    db: Session,
) -> list[activities_schema.Activity] | None:
    """Return every activity in the database, serialized.

    Note:
        Loads all rows in memory. Intended for migration
        scripts only — do not call from request handlers.

    Args:
        db: Database session.

    Returns:
        List of Activity schemas or None when empty.

    Raises:
        ProcessingError: On database error.
    """
    activities = db.execute(select(activities_models.Activity)).scalars().all()
    if not activities:
        return None
    return [activities_serializers.serialize_activity(a) for a in activities]


@core_decorators.handle_db_errors
def get_all_activities_for_migration(
    db: Session,
) -> list[activities_contracts.ActivityMigrationRef]:
    """Return a lightweight reference for every activity (migration use only).

    Projects only the identity, owner, provider ids, and time bounds the
    data-backfill migrations read, so no ORM row leaves the CRUD layer.

    Args:
        db: Database session.

    Returns:
        A migration reference per activity, or an empty list when there are none.

    Raises:
        ProcessingError: On database error.
    """
    activities = db.execute(select(activities_models.Activity)).scalars().all()
    return [
        activities_contracts.ActivityMigrationRef(
            id=activity.id,
            user_id=activity.user_id,
            start_time=activity.start_time,
            end_time=activity.end_time,
            strava_activity_id=activity.strava_activity_id,
            garminconnect_activity_id=activity.garminconnect_activity_id,
        )
        for activity in activities
    ]


@core_decorators.handle_db_errors
def get_user_activities(
    user_id: int,
    db: Session,
    activity_type: int | None = None,
    start_date: date | None = None,
    end_date: date | None = None,
    name_search: str | None = None,
    user_is_owner: bool = True,
    followee_ids: Sequence[int] | None = None,
) -> list[activities_schema.Activity] | None:
    """Get activities owned by a user (with optional filters).

    Args:
        user_id: Owner user ID.
        db: Database session.
        activity_type: Optional activity type filter.
        start_date: Optional inclusive start date filter.
        end_date: Optional inclusive end date filter.
        name_search: Optional case-insensitive name search.
        user_is_owner: When False, private (visibility=2) and
            hidden activities are excluded from the result.
        followee_ids: The requester's accepted-followee user ids, resolved
            by the caller; ``None`` for an owner-only or anonymous read.

    Returns:
        List of activity schemas or None when no matches.

    Raises:
        ProcessingError: On database error.
    """
    stmt = select(activities_models.Activity).where(activities_models.Activity.user_id == user_id)
    stmt = _apply_activity_visibility_filter(
        stmt,
        user_is_owner=user_is_owner,
        followee_ids=followee_ids,
    )
    if activity_type:
        stmt = stmt.where(activities_models.Activity.activity_type == activity_type)
    # Date filters are evaluated in each activity's own timezone, so a
    # user filtering "1 May" gets their 1 May, not UTC's.
    stmt = stmt.where(*activities_query.local_date_range_conditions(start_date, end_date, end_exclusive=False))
    if name_search:
        stmt = stmt.where(activities_query.name_search_condition(name_search))
    stmt = stmt.order_by(desc(activities_models.Activity.start_time))

    activities = db.execute(stmt).scalars().all()
    if not activities:
        return None
    return activities_serializers.serialize_and_mask(
        list(activities),
        requester_user_id=user_id if user_is_owner else None,
        force_non_owner=not user_is_owner,
    )


@core_decorators.handle_db_errors
def count_user_activities(
    user_id: int,
    db: Session,
    activity_type: int | None = None,
    start_date: date | None = None,
    end_date: date | None = None,
    name_search: str | None = None,
    user_is_owner: bool = True,
    followee_ids: Sequence[int] | None = None,
) -> int:
    """Count activities owned by a user (with optional filters).

    Mirrors :func:`get_user_activities`' filters with a SQL
    ``COUNT(*)`` so counting never loads or serializes rows.

    Args:
        user_id: Owner user ID.
        db: Database session.
        activity_type: Optional activity type filter.
        start_date: Optional inclusive start date filter.
        end_date: Optional inclusive end date filter.
        name_search: Optional case-insensitive name search.
        user_is_owner: When False, private (visibility=2) and
            hidden activities are excluded from the count.
        followee_ids: The requester's accepted-followee user ids, resolved
            by the caller; ``None`` for an owner-only or anonymous read.

    Returns:
        Number of matching activities.

    Raises:
        ProcessingError: On database error.
    """
    stmt = (
        select(func.count())
        .select_from(activities_models.Activity)
        .where(activities_models.Activity.user_id == user_id)
    )
    stmt = _apply_activity_visibility_filter(
        stmt,
        user_is_owner=user_is_owner,
        followee_ids=followee_ids,
    )
    if activity_type:
        stmt = stmt.where(activities_models.Activity.activity_type == activity_type)
    # Date filters are evaluated in each activity's own timezone, so a
    # user filtering "1 May" gets their 1 May, not UTC's.
    stmt = stmt.where(*activities_query.local_date_range_conditions(start_date, end_date, end_exclusive=False))
    if name_search:
        stmt = stmt.where(activities_query.name_search_condition(name_search))
    count = db.execute(stmt).scalar()
    return count or 0


@core_decorators.handle_db_errors
def get_user_activities_by_user_id_and_garminconnect_gear_set(
    user_id: int, db: Session
) -> list[activities_schema.Activity] | None:
    """Get activities for a user that have a Garmin gear ID.

    Args:
        user_id: Owner user ID.
        db: Database session.

    Returns:
        List of activity schemas or None when empty.

    Raises:
        ProcessingError: On database error.
    """
    stmt = (
        select(activities_models.Activity)
        .where(
            activities_models.Activity.user_id == user_id,
            activities_models.Activity.garminconnect_gear_id.isnot(None),
        )
        .order_by(desc(activities_models.Activity.start_time))
    )
    activities = db.execute(stmt).scalars().all()
    if not activities:
        return None
    return activities_serializers.serialize_and_mask(
        list(activities),
        requester_user_id=user_id,
    )


@core_decorators.handle_db_errors
def get_user_activities_with_pagination(
    user_id: int,
    db: Session,
    page_number: int = 1,
    num_records: int = 5,
    activity_type: int | None = None,
    start_date: date | None = None,
    end_date: date | None = None,
    name_search: str | None = None,
    sort_by: str | None = None,
    sort_order: str | None = None,
    user_is_owner: bool = False,
    followee_ids: Sequence[int] | None = None,
) -> list[activities_schema.Activity] | None:
    """Get a page of user activities with filters and sorting.

    Args:
        user_id: Owner user ID.
        db: Database session.
        page_number: 1-based page number.
        num_records: Records per page.
        activity_type: Optional activity type filter.
        start_date: Optional inclusive start date filter.
        end_date: Optional inclusive end date filter.
        name_search: Optional case-insensitive name search.
        sort_by: Optional sort key (see ``SORT_MAP``).
        sort_order: ``asc`` or ``desc``.
        user_is_owner: When False, private/hidden activities
            are excluded.
        followee_ids: The requester's accepted-followee user ids, resolved
            by the caller; ``None`` for an owner-only or anonymous read.

    Returns:
        List of activity schemas or None when empty.

    Raises:
        ProcessingError: On database error.
    """
    stmt = select(activities_models.Activity).where(
        activities_models.Activity.user_id == user_id,
    )
    stmt = _apply_activity_visibility_filter(
        stmt,
        user_is_owner=user_is_owner,
        followee_ids=followee_ids,
    )
    if activity_type:
        stmt = stmt.where(activities_models.Activity.activity_type == activity_type)
    # Date filters are evaluated in each activity's own timezone, so a
    # user filtering "1 May" gets their 1 May, not UTC's.
    stmt = stmt.where(*activities_query.local_date_range_conditions(start_date, end_date, end_exclusive=False))
    if name_search:
        stmt = stmt.where(activities_query.name_search_condition(name_search))

    stmt = stmt.order_by(*_sort_order_by(sort_by, sort_order))

    stmt = stmt.offset((page_number - 1) * num_records).limit(num_records)

    activities = db.execute(stmt).scalars().all()
    if not activities:
        return None
    return activities_serializers.serialize_and_mask(
        list(activities),
        requester_user_id=user_id if user_is_owner else None,
        force_non_owner=not user_is_owner,
    )


@core_decorators.handle_db_errors
def get_distinct_activity_types_for_user(user_id: int, db: Session) -> dict[int, str]:
    """Map distinct activity types owned by a user to names.

    Args:
        user_id: Owner user ID.
        db: Database session.

    Returns:
        Dict of activity_type -> human readable name.

    Raises:
        ProcessingError: On database error.
    """
    stmt = (
        select(activities_models.Activity.activity_type)
        .where(activities_models.Activity.user_id == user_id)
        .distinct()
        .order_by(activities_models.Activity.activity_type)
    )
    type_ids = db.execute(stmt).scalars().all()
    return {
        type_id: activities_constants.ACTIVITY_ID_TO_NAME.get(type_id, "Unknown")
        for type_id in type_ids
        if type_id is not None
    }


@core_decorators.handle_db_errors
def get_user_activities_per_timeframe(
    user_id: int,
    start: datetime,
    end: datetime,
    db: Session,
    user_is_owner: bool = False,
    followee_ids: Sequence[int] | None = None,
) -> list[activities_schema.Activity] | None:
    """Get a user's activities within a date range.

    Args:
        user_id: Owner user ID.
        start: Inclusive start datetime.
        end: Inclusive end datetime.
        db: Database session.
        user_is_owner: When False, private/hidden activities
            are excluded.
        followee_ids: The requester's accepted-followee user ids, resolved
            by the caller; ``None`` for an owner-only or anonymous read.

    Returns:
        List of activity schemas or None when empty.

    Raises:
        ProcessingError: On database error.
    """
    stmt = (
        select(activities_models.Activity)
        .where(
            activities_models.Activity.user_id == user_id,
            *activities_query.local_date_range_conditions(start.date(), end.date(), end_exclusive=False),
        )
        .order_by(desc(activities_models.Activity.start_time))
    )
    stmt = _apply_activity_visibility_filter(
        stmt,
        user_is_owner=user_is_owner,
        followee_ids=followee_ids,
    )
    activities = db.execute(stmt).scalars().all()
    if not activities:
        return None
    return activities_serializers.serialize_and_mask(
        list(activities),
        requester_user_id=user_id if user_is_owner else None,
        force_non_owner=not user_is_owner,
    )


@core_decorators.handle_db_errors
def get_user_activities_per_timeframe_and_activity_type(
    user_id: int,
    activity_type: int,
    start: datetime,
    end: datetime,
    db: Session,
    user_is_owner: bool = False,
    followee_ids: Sequence[int] | None = None,
) -> list[activities_schema.Activity] | None:
    """Get a user's activities within a date range by type.

    Args:
        user_id: Owner user ID.
        activity_type: Activity type to filter by.
        start: Inclusive start datetime.
        end: Inclusive end datetime.
        db: Database session.
        user_is_owner: When False, private/hidden activities
            are excluded.
        followee_ids: The requester's accepted-followee user ids, resolved
            by the caller; ``None`` for an owner-only or anonymous read.

    Returns:
        List of activity schemas or None when empty.

    Raises:
        ProcessingError: On database error.
    """
    stmt = (
        select(activities_models.Activity)
        .where(
            activities_models.Activity.user_id == user_id,
            activities_models.Activity.activity_type == activity_type,
            *activities_query.local_date_range_conditions(start.date(), end.date(), end_exclusive=False),
        )
        .order_by(desc(activities_models.Activity.start_time))
    )
    stmt = _apply_activity_visibility_filter(
        stmt,
        user_is_owner=user_is_owner,
        followee_ids=followee_ids,
    )
    activities = db.execute(stmt).scalars().all()
    if not activities:
        return None
    return activities_serializers.serialize_and_mask(
        list(activities),
        requester_user_id=user_id if user_is_owner else None,
        force_non_owner=not user_is_owner,
    )


@core_decorators.handle_db_errors
def get_user_activities_per_timeframe_and_activity_types(
    user_id: int,
    activity_types: list[int],
    start: datetime,
    end: datetime,
    db: Session,
    user_is_owner: bool = False,
    followee_ids: Sequence[int] | None = None,
    exclude_hidden: bool = False,
) -> list[activities_schema.Activity]:
    """Get a user's activities within a date range by types.

    Args:
        user_id: Owner user ID.
        activity_types: Activity types to include.
        start: Inclusive start datetime.
        end: Inclusive end datetime.
        db: Database session.
        user_is_owner: When False, private/hidden activities
            are excluded.
        followee_ids: The requester's accepted-followee user ids, resolved
            by the caller; ``None`` for an owner-only or anonymous read.
        exclude_hidden: When True, hidden activities are excluded
            even for owner requests.

    Returns:
        List of activity schemas.

    Raises:
        ProcessingError: On database error.
    """
    stmt = (
        select(activities_models.Activity)
        .where(
            activities_models.Activity.user_id == user_id,
            activities_models.Activity.activity_type.in_(activity_types),
            *activities_query.local_date_range_conditions(start.date(), end.date(), end_exclusive=False),
        )
        .order_by(desc(activities_models.Activity.start_time))
    )
    if exclude_hidden:
        stmt = stmt.where(activities_models.Activity.is_hidden.is_(False))
    stmt = _apply_activity_visibility_filter(
        stmt,
        user_is_owner=user_is_owner,
        followee_ids=followee_ids,
    )
    activities = db.execute(stmt).scalars().all()
    if not activities:
        return []
    return activities_serializers.serialize_and_mask(
        list(activities),
        requester_user_id=user_id if user_is_owner else None,
        force_non_owner=not user_is_owner,
    )


@core_decorators.handle_db_errors
def get_following_feed_after(
    followee_ids: list[int],
    after: tuple[datetime, int] | None,
    num_records: int,
    db: Session,
) -> list[activities_contracts.ActivityFeedEntry]:
    """Get the next keyset slice of the following feed.

    Ordered by ``(start_time DESC, id DESC)``. ``id`` is part of the key because
    ``start_time`` is not unique — two activities sharing a start time would
    otherwise straddle the boundary and one of them would be skipped or repeated.

    Args:
        followee_ids: The requester's accepted-followee user ids.
        after: The ``(start_time, id)`` position to resume strictly after, or
            ``None`` for the first slice.
        num_records: Maximum records to return.
        db: Database session.

    Returns:
        The slice, newest first (empty when there is nothing more).
    """
    if not followee_ids:
        return []
    stmt = select(activities_models.Activity).where(
        activities_models.Activity.user_id.in_(followee_ids),
        activities_models.Activity.visibility.in_([0, 1]),
        activities_models.Activity.is_hidden.is_(False),
        _is_not_live_strava_api_activity(),
    )
    if after is not None:
        last_start_time, last_id = after
        # Row-value comparison: strictly older, or same instant with a lower id.
        stmt = stmt.where(
            tuple_(activities_models.Activity.start_time, activities_models.Activity.id)
            < tuple_(literal(last_start_time), literal(last_id))
        )
    stmt = stmt.order_by(desc(activities_models.Activity.start_time), desc(activities_models.Activity.id)).limit(
        num_records
    )
    activities = db.execute(stmt).scalars().all()
    if not activities:
        return []
    masked = activities_serializers.serialize_and_mask(list(activities), force_non_owner=True)
    return [
        activities_contracts.ActivityFeedEntry(
            activity=item,
            cursor_start_time=orm_activity.start_time,
            cursor_id=orm_activity.id,
        )
        for orm_activity, item in zip(activities, masked, strict=True)
    ]


@core_decorators.handle_db_errors
def get_gear_activities_count_by_user_id(
    user_id: int,
    gear_id: int,
    db: Session,
) -> int:
    """Count activities for a gear owned by user.

    Args:
        user_id: Owner user ID.
        gear_id: Gear ID.
        db: Database session.

    Returns:
        Number of activities for the gear.

    Raises:
        ProcessingError: On database error.
    """
    stmt = (
        select(func.count())
        .select_from(activities_models.Activity)
        .where(
            activities_models.Activity.user_id == user_id,
            activities_models.Activity.gear_id == gear_id,
        )
    )
    count = db.execute(stmt).scalar()
    return count or 0


@core_decorators.handle_db_errors
def get_user_activities_by_gear_id_and_user_id(
    user_id: int, gear_id: int, db: Session
) -> list[activities_schema.Activity] | None:
    """Get all activities for a gear owned by a user.

    Args:
        user_id: Owner user ID.
        gear_id: Gear ID.
        db: Database session.

    Returns:
        List of activity schemas or None when empty.

    Raises:
        ProcessingError: On database error.
    """
    stmt = (
        select(activities_models.Activity)
        .where(
            activities_models.Activity.user_id == user_id,
            activities_models.Activity.gear_id == gear_id,
        )
        .order_by(desc(activities_models.Activity.start_time))
    )
    activities = db.execute(stmt).scalars().all()
    if not activities:
        return None
    return activities_serializers.serialize_and_mask(
        list(activities),
        requester_user_id=user_id,
    )


@core_decorators.handle_db_errors
def get_user_activities_by_gear_id_and_user_id_with_pagination(
    user_id: int,
    gear_id: int,
    page_number: int,
    num_records: int,
    db: Session,
) -> list[activities_schema.Activity] | None:
    """Get a page of activities for a gear owned by a user.

    Args:
        user_id: Owner user ID.
        gear_id: Gear ID.
        page_number: 1-based page number.
        num_records: Records per page.
        db: Database session.

    Returns:
        List of activity schemas or None when empty.

    Raises:
        ProcessingError: On database error.
    """
    stmt = (
        select(activities_models.Activity)
        .where(
            activities_models.Activity.user_id == user_id,
            activities_models.Activity.gear_id == gear_id,
        )
        .order_by(desc(activities_models.Activity.start_time))
        .offset((page_number - 1) * num_records)
        .limit(num_records)
    )
    activities = db.execute(stmt).scalars().all()
    if not activities:
        return None
    return activities_serializers.serialize_and_mask(
        list(activities),
        requester_user_id=user_id,
    )


@core_decorators.handle_db_errors
def sum_gear_usage(gear_id: int, db: Session) -> activities_contracts.ActivityUsageTotals:
    """Total distance and moving time recorded against a gear.

    Lives here rather than in the gears module so the activities table is only
    ever queried by its owner.

    Args:
        gear_id: The gear to accumulate usage for.
        db: Database session.

    Returns:
        The gear's totals; zeroes when it has no activities.

    Raises:
        ProcessingError: On database error.
    """
    stmt = select(
        func.coalesce(func.sum(activities_models.Activity.distance), 0),
        func.coalesce(func.sum(activities_models.Activity.total_timer_time), 0),
    ).where(activities_models.Activity.gear_id == gear_id)
    distance, moving_time = db.execute(stmt).one()
    return activities_contracts.ActivityUsageTotals(distance=float(distance), time=float(moving_time))


@core_decorators.handle_db_errors
def sum_gear_usage_by_window(
    gear_id: int,
    windows: Sequence[activities_contracts.GearUsageWindow],
    db: Session,
) -> dict[int, activities_contracts.ActivityUsageTotals]:
    """Total distance and moving time per date window for one gear.

    Answers "how far has each component of this gear been ridden?" in a single
    pass over the gear's activities: each window contributes a pair of conditional
    sums, so adding a component costs two more aggregate expressions rather than
    another round trip. Windows are matched against each activity's **local** date
    (see :class:`~modules.activities.activity.contracts.GearUsageWindow`).

    Args:
        gear_id: The gear whose activities to accumulate.
        windows: The date windows to accumulate over, keyed by the caller.
        db: Database session.

    Returns:
        Totals per window key. Windows with no matching activity report zeroes,
        so every requested key is always present.

    Raises:
        ProcessingError: On database error.
    """
    if not windows:
        return {}

    local_date = func.date(activities_query.local_start_time_expression())

    columns = []
    for window in windows:
        in_window = local_date >= window.start_date
        if window.end_date is not None:
            in_window = and_(in_window, local_date <= window.end_date)
        columns.append(func.coalesce(func.sum(case((in_window, activities_models.Activity.distance), else_=0)), 0))
        columns.append(
            func.coalesce(func.sum(case((in_window, activities_models.Activity.total_timer_time), else_=0)), 0)
        )

    stmt = select(*columns).where(activities_models.Activity.gear_id == gear_id)
    row = db.execute(stmt).one()

    return {
        window.key: activities_contracts.ActivityUsageTotals(
            distance=float(row[index * 2]),
            time=float(row[index * 2 + 1]),
        )
        for index, window in enumerate(windows)
    }


@core_decorators.handle_db_errors
def get_activity_by_id_from_user_id_or_has_visibility(
    activity_id: int, user_id: int, db: Session, followee_ids: Sequence[int] | None = None
) -> activities_schema.Activity | None:
    """Get an activity by ID if owned or visible to the user.

    Args:
        activity_id: Activity ID.
        user_id: Requesting user ID.
        db: Database session.
        followee_ids: The requester's accepted-followee user ids, resolved by
            the caller.

    Returns:
        Activity schema or None if not found / not visible.

    Raises:
        ProcessingError: On database error.
    """
    stmt = select(activities_models.Activity).where(
        or_(
            activities_models.Activity.user_id == user_id,
            _visible_to_requester_condition(followee_ids),
        ),
        activities_models.Activity.id == activity_id,
    )
    activity = db.execute(stmt).scalar_one_or_none()
    if not activity:
        return None
    schema = activities_serializers.serialize_activity(activity)
    is_owner = activity.user_id == user_id
    activities_serializers.apply_visibility_mask(schema, is_owner=is_owner)
    return schema


@core_decorators.handle_db_errors
def get_viewable_activity_by_id_for_user(
    activity_id: int, user_id: int, db: Session, followee_ids: Sequence[int] | None = None
) -> activities_schema.Activity | None:
    """Return an activity (unmasked) iff the user may view it — child-resource authz gate.

    Enforces the same visibility rule as
    :func:`get_activity_by_id_from_user_id_or_has_visibility` (the requester must
    own the activity, or it must be public, or followers-only with an accepted
    follow — never private or hidden for a non-owner), but returns the activity
    **without** applying the field mask so child sub-resource reads (streams /
    laps / sets / workout-steps) can still inspect the activity's ``hide_*`` flags
    and ``timezone`` to apply their own per-field masking.

    This is the authorization gate for child sub-resources: it stops a non-owner
    from reading a private or followers-only activity's streams/laps/sets/steps by
    ID (OWASP A01 / IDOR). Prefer it over :func:`get_activity_by_id` (which does no
    permission check) whenever a request-facing read is scoped to a requester.

    Args:
        activity_id: Activity ID.
        user_id: Requesting user ID.
        db: Database session.
        followee_ids: The requester's accepted-followee user ids, resolved by
            the caller.

    Returns:
        The activity schema when the user may view it, otherwise ``None``.

    Raises:
        ProcessingError: On database error.
    """
    stmt = select(activities_models.Activity).where(
        or_(
            activities_models.Activity.user_id == user_id,
            _visible_to_requester_condition(followee_ids),
        ),
        activities_models.Activity.id == activity_id,
    )
    activity = db.execute(stmt).scalar_one_or_none()
    if not activity:
        return None
    return activities_serializers.serialize_activity(activity)


@core_decorators.handle_db_errors
def get_activity_by_id_if_is_public(activity_id: int, db: Session) -> activities_schema.Activity | None:
    """Get an activity by ID if it is publicly shareable.

    Answers only the row-level question. Whether the server allows public
    shareable links at all is a policy the caller checks first — asking another
    module mid-``SELECT`` is a service decision, not a persistence one.

    Args:
        activity_id: Activity ID.
        db: Database session.

    Returns:
        Activity schema or None when not public / not found.

    Raises:
        ProcessingError: On database error.
    """
    stmt = select(activities_models.Activity).where(
        activities_models.Activity.visibility == 0,
        activities_models.Activity.is_hidden.is_(False),
        _is_not_live_strava_api_activity(),
        activities_models.Activity.id == activity_id,
    )
    activity = db.execute(stmt).scalar_one_or_none()
    if not activity:
        return None
    schema = activities_serializers.serialize_activity(activity)
    activities_serializers.apply_visibility_mask(schema, is_owner=False)
    return schema


def get_public_activity_for_child_read(
    activity_id: int,
    db: Session,
    *,
    hide_attr: str,
) -> activities_schema.Activity | None:
    """Return a publicly readable activity for an unauthenticated child-resource read.

    The single public gate for activity sub-resources (laps / sets / workout
    steps / streams). It composes the two checks that must *both* hold before any
    child rows are served anonymously:

    1. The activity itself is publicly shareable — delegated to
       :func:`get_activity_by_id_if_is_public`, which enforces ``visibility == 0``
       **and** ``is_hidden is False``. The server-wide ``public_shareable_links``
       setting is checked by the caller, before this is reached.
    2. The per-activity privacy flag guarding this particular child resource
       (e.g. ``hide_laps``, ``hide_workout_sets_steps``) is not set.

    Each child CRUD previously hand-rolled step 1, and every copy omitted the
    ``is_hidden`` check — so a hidden (duplicate-start-time) activity returned
    ``null`` from the public activity endpoint while still serving its laps, sets
    and workout steps to anonymous callers (OWASP A01: broken access control).
    Routing every child through this one function makes that divergence
    impossible to reintroduce by copy-paste.

    Args:
        activity_id: Activity ID being read.
        db: Database session.
        hide_attr: Name of the boolean ``hide_*`` attribute on the activity
            schema that gates this child resource.

    Returns:
        The public activity schema when the child rows may be served anonymously,
        otherwise ``None``.

    Raises:
        ProcessingError: On database error.
    """
    activity = get_activity_by_id_if_is_public(activity_id, db)
    if activity is None:
        return None

    if getattr(activity, hide_attr):
        return None

    return activity


@core_decorators.handle_db_errors
def get_activity_by_id(activity_id: int, db: Session) -> activities_schema.Activity | None:
    """Get an activity by ID without permission checks.

    Args:
        activity_id: Activity ID.
        db: Database session.

    Returns:
        Activity schema or None when not found.

    Raises:
        ProcessingError: On database error.
    """
    stmt = select(activities_models.Activity).where(
        activities_models.Activity.id == activity_id,
    )
    activity = db.execute(stmt).scalar_one_or_none()
    if not activity:
        return None
    return activities_serializers.serialize_activity(activity)


@core_decorators.handle_db_errors
def get_activity_by_start_time(
    start_time: str | datetime, user_id: int, db: Session
) -> activities_schema.Activity | None:
    """Get a user's activity matching a specific start time.

    Args:
        start_time: ISO-format string or datetime.
        user_id: Owner user ID.
        db: Database session.

    Returns:
        Activity schema or None when not found.

    Raises:
        ProcessingError: On database error.
    """
    if isinstance(start_time, str):
        start_time = datetime.fromisoformat(start_time)
    if start_time.tzinfo is None:
        start_time = start_time.replace(tzinfo=UTC)
    stmt = select(activities_models.Activity).where(
        activities_models.Activity.user_id == user_id,
        activities_models.Activity.start_time == start_time,
    )
    activity = db.execute(stmt).scalar_one_or_none()
    if not activity:
        return None
    return activities_serializers.serialize_activity(activity)


@core_decorators.handle_db_errors
def get_activity_by_dedup_key(dedup_key: str, user_id: int, db: Session) -> activities_schema.Activity | None:
    """Get a user's activity by its idempotency dedup key.

    Used by the ingestion seam to make re-import of an already-ingested activity
    a no-op: a provider-scoped id now, a content hash later.

    Args:
        dedup_key: Stable idempotency key (e.g. ``"strava:123"``).
        user_id: Owner user ID.
        db: Database session.

    Returns:
        Activity schema or None when not found.

    Raises:
        ProcessingError: On database error.
    """
    stmt = select(activities_models.Activity).where(
        activities_models.Activity.user_id == user_id,
        activities_models.Activity.dedup_key == dedup_key,
    )
    activity = db.execute(stmt).scalars().first()
    if not activity:
        return None
    return activities_serializers.serialize_activity(activity)


@core_decorators.handle_db_errors
def get_user_activity_ids(activity_ids: list[int], user_id: int, db: Session) -> list[int]:
    """Return the subset of the given activity ids owned by the user.

    The ownership half of a child-collection read, answered by the package that
    owns the parent table so no child CRUD has to join it.

    Args:
        activity_ids: Candidate activity IDs.
        user_id: Owner user ID.
        db: Database session.

    Returns:
        The owned ids, in no particular order; empty when none match.

    Raises:
        ProcessingError: On database error.
    """
    if not activity_ids:
        return []
    stmt = select(activities_models.Activity.id).where(
        activities_models.Activity.user_id == user_id,
        activities_models.Activity.id.in_(activity_ids),
    )
    return list(db.scalars(stmt).all())


def _to_scoring_context(row) -> activities_contracts.ActivityScoringContext:
    """Convert one activity projection row to its scoring context."""
    activity_id, owner_id, total_timer_time = row
    return activities_contracts.ActivityScoringContext(
        activity_id=activity_id,
        owner_id=owner_id,
        total_timer_time=float(total_timer_time) if total_timer_time is not None else None,
    )


@core_decorators.handle_db_errors
def get_activity_scoring_context(
    activity_id: int,
    db: Session,
) -> activities_contracts.ActivityScoringContext | None:
    """Return parent columns needed to score an activity's streams."""
    stmt = select(
        activities_models.Activity.id,
        activities_models.Activity.user_id,
        activities_models.Activity.total_timer_time,
    ).where(activities_models.Activity.id == activity_id)
    row = db.execute(stmt).first()
    return _to_scoring_context(row) if row is not None else None


@core_decorators.handle_db_errors
def get_activity_scoring_contexts(
    activity_ids: list[int],
    db: Session,
) -> dict[int, activities_contracts.ActivityScoringContext]:
    """Return scoring contexts keyed by activity id."""
    if not activity_ids:
        return {}
    stmt = select(
        activities_models.Activity.id,
        activities_models.Activity.user_id,
        activities_models.Activity.total_timer_time,
    ).where(activities_models.Activity.id.in_(activity_ids))
    contexts = (_to_scoring_context(row) for row in db.execute(stmt).all())
    return {context.activity_id: context for context in contexts}


@core_decorators.handle_db_errors
def list_user_activity_scoring_contexts(
    user_id: int,
    db: Session,
    *,
    after_id: int = 0,
    batch_size: int = 500,
) -> list[activities_contracts.ActivityScoringContext]:
    """Return an id-ordered batch of one user's activity scoring contexts."""
    stmt = (
        select(
            activities_models.Activity.id,
            activities_models.Activity.user_id,
            activities_models.Activity.total_timer_time,
        )
        .where(
            activities_models.Activity.user_id == user_id,
            activities_models.Activity.id > after_id,
        )
        .order_by(activities_models.Activity.id)
        .limit(batch_size)
    )
    return [_to_scoring_context(row) for row in db.execute(stmt).all()]


@core_decorators.handle_db_errors
def get_activity_by_id_from_user_id(activity_id: int, user_id: int, db: Session) -> activities_schema.Activity | None:
    """Get a user's activity by ID.

    Args:
        activity_id: Activity ID.
        user_id: Owner user ID.
        db: Database session.

    Returns:
        Activity schema or None when not found.

    Raises:
        ProcessingError: On database error.
    """
    stmt = select(activities_models.Activity).where(
        activities_models.Activity.user_id == user_id,
        activities_models.Activity.id == activity_id,
    )
    activity = db.execute(stmt).scalar_one_or_none()
    if not activity:
        return None
    return activities_serializers.serialize_activity(activity)


@core_decorators.handle_db_errors
def get_activity_by_strava_id_from_user_id(
    activity_strava_id: int, user_id: int, db: Session
) -> activities_schema.Activity | None:
    """Get a user's activity by its Strava activity ID.

    Args:
        activity_strava_id: Strava activity ID.
        user_id: Owner user ID.
        db: Database session.

    Returns:
        Activity schema or None when not found.

    Raises:
        ProcessingError: On database error.
    """
    stmt = select(activities_models.Activity).where(
        activities_models.Activity.user_id == user_id,
        activities_models.Activity.strava_activity_id == activity_strava_id,
    )
    activity = db.execute(stmt).scalar_one_or_none()
    if not activity:
        return None
    return activities_serializers.serialize_activity(activity)


@core_decorators.handle_db_errors
def get_activity_by_garminconnect_id_from_user_id(
    activity_garminconnect_id: int, user_id: int, db: Session
) -> activities_schema.Activity | None:
    """Get a user's activity by its Garmin Connect activity ID.

    Args:
        activity_garminconnect_id: Garmin Connect activity ID.
        user_id: Owner user ID.
        db: Database session.

    Returns:
        Activity schema or None when not found.

    Raises:
        ProcessingError: On database error.
    """
    stmt = select(activities_models.Activity).where(
        activities_models.Activity.user_id == user_id,
        activities_models.Activity.garminconnect_activity_id == activity_garminconnect_id,
    )
    activity = db.execute(stmt).scalars().first()
    if not activity:
        return None
    return activities_serializers.serialize_activity(activity)


@core_decorators.handle_db_errors
def create_activity(
    activity: activities_contracts.ActivityCore,
    db: Session,
    *,
    commit: bool = True,
    dedup_key: str | None = None,
) -> activities_schema.Activity:
    """Persist a new activity; duplicate start-times are marked hidden.

    Pure persistence: notifications and derived work (thumbnails, HR zones) are
    decoupled to ``activity.created`` subscribers. The caller publishes
    the event after the activity's children are stored; this function only writes
    the row and flags start-time duplicates as hidden.

    Args:
        activity: Strict ``ActivityCore`` ingestion schema to persist.
        db: Database session.
        dedup_key: Optional stable idempotency key stored on the row so future
            re-imports of the same source can be recognised as duplicates.

    Returns:
        The stored activity as the read schema, with the generated ``id`` and
        ``created_at`` populated from the row. ``is_hidden`` is ``True`` when the
        start time duplicates an existing activity — the signal the caller
        forwards to the ``activity.created`` notification subscriber.

    Raises:
        ProcessingError: On database error.
    """
    if activity.user_id is None:
        raise core_exceptions.InvalidInputError("Activity user_id is required")

    # Normalize the start time to a UTC-aware datetime at the persistence
    # boundary. Parsers emit naive UTC wall-clock values and providers emit
    # ISO strings; to_utc_aware coerces both to aware UTC and returns None for
    # a missing value, so we never persist or compare a naive/absent start
    # time (this is also what keeps get_activity_by_start_time from being
    # handed a None).
    normalized_start_time = core_timezone.to_utc_aware(activity.start_time)
    if normalized_start_time is None:
        raise core_exceptions.InvalidInputError("Activity start_time is required and must be a valid datetime")

    activity_start_time_exists = get_activity_by_start_time(normalized_start_time, activity.user_id, db)

    new_activity = activities_serializers.deserialize_activity(activity)
    # Flagged on the ORM row rather than on the caller's input: ``create_activity``
    # takes the write contract and must not mutate it (nor could it set the read
    # model's ``id``/``created_at`` there — those fields do not exist on the
    # ingestion shape at all).
    if activity_start_time_exists:
        new_activity.is_hidden = True
    # Persist the idempotency key alongside the row so future re-imports of
    # the same source can be recognised as duplicates.
    new_activity.dedup_key = dedup_key

    db.add(new_activity)
    # Persist the row so its generated id / created_at are available. On the
    # ingestion path the caller drives a single commit for the whole unit of
    # work (activity + children + outbox row), so we only flush here; other
    # callers keep the default commit=True.
    if commit:
        db.commit()
    else:
        db.flush()
    db.refresh(new_activity)

    # Build the read schema from the stored row. Returning a freshly serialized
    # ``Activity`` (rather than handing back the mutated input) is what makes the
    # declared ``ActivityCore -> Activity`` signature true: the generated id and
    # ``created_at`` belong to the read model, which the ingestion contract
    # deliberately does not carry.
    created = activities_serializers.serialize_activity(new_activity)

    return created


@core_decorators.handle_db_errors
def set_activity_thumbnail_path(
    activity_id: int,
    thumbnail_path: str | None,
    db: Session,
) -> None:
    """Set the map thumbnail path for an activity.

    Args:
        activity_id: Target activity ID.
        thumbnail_path: Absolute path to the thumbnail file.
        db: Database session.

    Returns:
        None

    Raises:
        ProcessingError: On database error.
    """
    stmt = select(activities_models.Activity).where(activities_models.Activity.id == activity_id)
    db_activity = db.execute(stmt).scalar_one_or_none()
    if db_activity is None:
        logger.warning(
            "Activity not found when setting the thumbnail path",
            extra=core_logger.context(activity_id=activity_id),
        )
        return
    db_activity.map_thumbnail_path = thumbnail_path
    db.commit()


@core_decorators.handle_db_errors
def update_activity_location(
    activity_id: int,
    city: str | None,
    town: str | None,
    country: str | None,
    db: Session,
) -> bool:
    """Persist a reverse-geocoded location on an activity.

    Written by the geocoding subscriber / backfill once the location for a GPS
    activity has been resolved (geocoding no longer runs inline in the parsers).

    Args:
        activity_id: Target activity ID.
        city: Resolved city, or None.
        town: Resolved town, or None.
        country: Resolved country, or None.
        db: Database session.

    Returns:
        True when the activity existed and was updated, False when it was not
        found.

    Raises:
        ProcessingError: On database error.
    """
    stmt = select(activities_models.Activity).where(activities_models.Activity.id == activity_id)
    db_activity = db.execute(stmt).scalar_one_or_none()
    if db_activity is None:
        logger.warning(
            "Activity not found when updating the location",
            extra=core_logger.context(activity_id=activity_id),
        )
        return False
    db_activity.city = city
    db_activity.town = town
    db_activity.country = country
    db.commit()
    return True


def get_activities_missing_location(
    db: Session,
    limit: int = 200,
) -> list[activities_contracts.ActivityLocationRef]:
    """Return references to activities that have no resolved location.

    Rows where ``city``, ``town`` and ``country`` are all NULL — candidates for
    the reverse-geocoding backfill. Bounded by ``limit`` so a single backfill
    pass makes at most ``limit`` (rate-limited) geocoding requests; the
    remainder are picked up on the next scheduled run.

    Args:
        db: Database session.
        limit: Maximum number of candidate rows to return.

    Returns:
        Location references (id only) ordered by id, or an empty list on error.
    """
    try:
        stmt = (
            select(activities_models.Activity.id)
            .where(
                activities_models.Activity.city.is_(None),
                activities_models.Activity.town.is_(None),
                activities_models.Activity.country.is_(None),
            )
            .order_by(activities_models.Activity.id)
            .limit(limit)
        )
        ids = db.execute(stmt).scalars().all()
        return [activities_contracts.ActivityLocationRef(id=activity_id) for activity_id in ids]
    except SQLAlchemyError as err:
        logger.error(
            "Database error in get_activities_missing_location",
            exc_info=err,
            extra=core_logger.context(error=type(err).__name__),
        )
        return []


def clear_all_activity_thumbnail_paths(db: Session) -> None:
    """Set ``map_thumbnail_path`` to NULL on every activity.

    Args:
        db: Database session.

    Returns:
        None
    """
    try:
        db.execute(sa_update(activities_models.Activity).values(map_thumbnail_path=None))
        db.commit()
    except SQLAlchemyError as err:
        db.rollback()
        logger.error(
            "Database error in clear_all_activity_thumbnail_paths",
            exc_info=err,
            extra=core_logger.context(error=type(err).__name__),
        )


def get_activities_with_thumbnail(
    db: Session,
) -> list[activities_contracts.ActivityThumbnailRef]:
    """Return references to activities that have a map thumbnail.

    Args:
        db: Database session.

    Returns:
        Thumbnail references (id + stored key) for rows with
        ``map_thumbnail_path`` set, or an empty list on error.
    """
    try:
        stmt = select(activities_models.Activity).where(activities_models.Activity.map_thumbnail_path.isnot(None))
        rows = db.execute(stmt).scalars().all()
        return [
            activities_contracts.ActivityThumbnailRef(id=row.id, map_thumbnail_path=row.map_thumbnail_path)
            for row in rows
        ]
    except SQLAlchemyError as err:
        logger.error(
            "Database error in get_activities_with_thumbnail",
            exc_info=err,
            extra=core_logger.context(error=type(err).__name__),
        )
        return []


def get_activities_without_thumbnail(
    db: Session,
) -> list[activities_contracts.ActivityThumbnailRef]:
    """Return references to activities that have no map thumbnail.

    Args:
        db: Database session.

    Returns:
        Thumbnail references (id, with a null key) for rows with
        ``map_thumbnail_path`` set to NULL, or an empty list on error.
    """
    try:
        stmt = select(activities_models.Activity).where(activities_models.Activity.map_thumbnail_path.is_(None))
        rows = db.execute(stmt).scalars().all()
        return [
            activities_contracts.ActivityThumbnailRef(id=row.id, map_thumbnail_path=row.map_thumbnail_path)
            for row in rows
        ]
    except SQLAlchemyError as err:
        logger.error(
            "Database error in get_activities_without_thumbnail",
            exc_info=err,
            extra=core_logger.context(error=type(err).__name__),
        )
        return []


def get_activities_with_legacy_thumbnail_path(
    db: Session,
    after_id: int = 0,
    limit: int = 200,
) -> list[activities_contracts.ActivityThumbnailRef]:
    """Return references to activities whose thumbnail value is a legacy filesystem path.

    Legacy values are absolute paths (they contain a ``/`` separator); the new
    storage keys (e.g. ``42.webp``) never do. Ordered by id and paged via
    ``after_id`` so migration 8 can process them in bounded batches (migration
    use only).

    Args:
        db: Database session.
        after_id: Return only activities with ``id`` greater than this.
        limit: Maximum number of rows to return.

    Returns:
        Thumbnail references (id + stored key) for rows with a legacy thumbnail
        path, or an empty list on error.
    """
    try:
        stmt = (
            select(activities_models.Activity)
            .where(
                activities_models.Activity.map_thumbnail_path.isnot(None),
                activities_models.Activity.map_thumbnail_path.like("%/%"),
                activities_models.Activity.id > after_id,
            )
            .order_by(activities_models.Activity.id)
            .limit(limit)
        )
        rows = db.execute(stmt).scalars().all()
        return [
            activities_contracts.ActivityThumbnailRef(id=row.id, map_thumbnail_path=row.map_thumbnail_path)
            for row in rows
        ]
    except SQLAlchemyError as err:
        logger.error(
            "Database error in get_activities_with_legacy_thumbnail_path",
            exc_info=err,
            extra=core_logger.context(error=type(err).__name__),
        )
        return []


@core_decorators.handle_db_errors
def edit_activity(
    user_id: int,
    activity_id: int,
    activity_attributes: activities_schema.ActivityEdit | activities_schema.Activity,
    db: Session,
    commit: bool = True,
) -> activities_schema.Activity:
    """Apply partial updates to a user's activity.

    Args:
        user_id: Owner user ID.
        activity_id: ID of the activity to update (from the request path).
        activity_attributes: Pydantic model carrying the fields to update;
            only the fields explicitly set are applied.
        db: Database session.
        commit: When True (default) commit immediately. Pass False to stage the
            update in the caller's unit of work so ``activity.updated`` can be
            published atomically with it.

    Returns:
        The updated activity as a serialized schema.

    Raises:
        NotFoundError: When the activity is missing.
        ProcessingError: On database error.
    """
    stmt = select(activities_models.Activity).where(
        activities_models.Activity.user_id == user_id,
        activities_models.Activity.id == activity_id,
    )
    db_activity = db.execute(stmt).scalar_one_or_none()
    if db_activity is None:
        raise core_exceptions.NotFoundError("Activity not found")

    # Both `Activity` and `ActivityEdit` are Pydantic models;
    # `exclude_unset=True` lets callers explicitly clear nullable
    # fields (e.g. private_notes=None) without being silently
    # discarded as the previous `vars()` filter did.
    if not isinstance(activity_attributes, BaseModel):
        raise TypeError("activity_attributes must be a Pydantic model")
    activity_data = activity_attributes.model_dump(exclude_unset=True)

    if "description" in activity_data:
        activity_data["description"] = core_sanitization.sanitize_markdown(activity_data["description"])
    if "private_notes" in activity_data:
        activity_data["private_notes"] = core_sanitization.sanitize_markdown(activity_data["private_notes"])

    # ``id`` is the primary key — never overwrite it
    activity_data.pop("id", None)

    for key, value in activity_data.items():
        setattr(db_activity, key, value)

    if commit:
        db.commit()
    else:
        # The version bump lives in the ORM's UPDATE, so flush before reading it
        # back — the caller serializes this row into its response and would
        # otherwise hand out a stale ETag.
        db.flush()
    db.refresh(db_activity)
    return activities_serializers.serialize_activity(db_activity)


@core_decorators.handle_db_errors
def edit_user_activities_visibility(user_id: int, visibility: int, db: Session, commit: bool = True) -> list[int]:
    """Bulk-update the visibility for every activity of a user.

    Args:
        user_id: Owner user ID.
        visibility: New visibility value (0, 1, 2).
        db: Database session.
        commit: When True (default) commit immediately. Pass False to stage the
            update in the caller's unit of work so one ``activity.updated`` per
            changed row can be published atomically with it.

    Returns:
        The IDs of the updated activities, so the caller can publish one event
        per row instead of re-deriving which activities the user owns.

    Raises:
        ProcessingError: On database error.
    """
    stmt = (
        sa_update(activities_models.Activity)
        .where(activities_models.Activity.user_id == user_id)
        # Core UPDATEs bypass the ORM version bump, so an ETag would survive a
        # change it should have invalidated.
        .values(visibility=visibility, version=activities_models.Activity.version + 1)
        .returning(activities_models.Activity.id)
    )
    updated_ids = [row_id for (row_id,) in db.execute(stmt).all()]
    if commit:
        db.commit()
    return updated_ids


@core_decorators.handle_db_errors
def bulk_set_activities_gear_id(
    user_id: int,
    gear_assignments: dict[int, int | None],
    db: Session,
    commit: bool = True,
) -> list[int]:
    """Bulk-update ``gear_id`` for many activities owned by a user.

    Assignments are grouped by target ``gear_id`` so the database
    only sees one ``UPDATE`` per distinct gear value, regardless
    of how many activities are being updated. Ownership is enforced
    in the ``WHERE`` clause so activities belonging to other users
    are silently ignored.

    Args:
        user_id: Owner user ID.
        gear_assignments: Mapping of ``activity_id`` -> ``gear_id``
            (use ``None`` to clear the gear assignment).
        db: Database session.
        commit: When True (default) commit immediately. Pass False to stage the
            updates in the caller's unit of work.

    Returns:
        The IDs of the activities actually updated — a subset of the requested
        keys, since the ownership predicate silently drops another user's ids.

    Raises:
        ProcessingError: On database error.
    """
    if not gear_assignments:
        return []
    by_gear: dict[int | None, list[int]] = defaultdict(list)
    for activity_id, gear_id in gear_assignments.items():
        by_gear[gear_id].append(activity_id)

    updated_ids: list[int] = []
    for gear_id, activity_ids in by_gear.items():
        stmt = (
            sa_update(activities_models.Activity)
            .where(
                activities_models.Activity.user_id == user_id,
                activities_models.Activity.id.in_(activity_ids),
            )
            .values(gear_id=gear_id, version=activities_models.Activity.version + 1)
            .returning(activities_models.Activity.id)
        )
        updated_ids.extend(row_id for (row_id,) in db.execute(stmt).all())
    if commit:
        db.commit()
    return updated_ids


@core_decorators.handle_db_errors
def update_activity_gear_id(
    activity_id: int,
    user_id: int,
    gear_id: int | None,
    db: Session,
) -> None:
    """Set the gear_id on a single activity.

    Args:
        activity_id: Activity ID.
        user_id: Owner user ID.
        gear_id: Gear ID to associate, or None to clear.
        db: Database session.

    Returns:
        None

    Raises:
        ProcessingError: On database error.
    """
    stmt = (
        sa_update(activities_models.Activity)
        .where(
            activities_models.Activity.id == activity_id,
            activities_models.Activity.user_id == user_id,
        )
        .values(gear_id=gear_id, version=activities_models.Activity.version + 1)
    )
    db.execute(stmt)
    db.commit()


@core_decorators.handle_db_errors
def delete_activity(activity_id: int, user_id: int, db: Session, commit: bool = True) -> None:
    """Delete an activity owned by ``user_id``.

    Ownership is part of the ``WHERE`` clause rather than a precondition the
    caller is trusted to have checked: a delete that does not match the owner
    affects zero rows and raises 404, so a caller that forgets to pre-fetch the
    activity cannot turn this into an IDOR (OWASP A01). The 404 is deliberately
    indistinguishable from "no such activity" so it does not disclose the
    existence of another user's activity.

    Args:
        activity_id: Activity ID.
        user_id: ID of the user that must own the activity.
        db: Database session.
        commit: When True (default) commit immediately. Pass False to stage the
            delete in the caller's unit of work so ``activity.deleted`` can be
            published atomically with it (the durable outbox row joins the same
            transaction via ``publish_committing``).

    Returns:
        None

    Raises:
        NotFoundError: When the activity is missing or not owned by ``user_id``.
        ProcessingError: On database error.
    """
    try:
        stmt = sa_delete(activities_models.Activity).where(
            activities_models.Activity.id == activity_id,
            activities_models.Activity.user_id == user_id,
        )
        result = cast("CursorResult[Any]", db.execute(stmt))
        if result.rowcount == 0:
            raise core_exceptions.NotFoundError(f"Activity with id {activity_id} not found")
        if commit:
            db.commit()
    except core_exceptions.NotFoundError:
        # Kept rather than delegated: the 404 above is raised *after* the DELETE
        # has been staged, and the decorator does not roll back for a domain
        # error. Callers pass ``commit=False`` to stage the delete in their own
        # unit of work, so without this the aborted delete would linger in their
        # transaction.
        db.rollback()
        raise


@core_decorators.handle_db_errors
def delete_all_strava_activities_for_user(user_id: int, db: Session, commit: bool = True) -> list[int]:
    """Delete every Strava-synced activity owned by a user.

    Args:
        user_id: Owner user ID.
        db: Database session.
        commit: When True (default) commit immediately. Pass False to stage the
            deletes in the caller's unit of work so one ``activity.deleted`` per
            removed row can be published atomically with them.

    Returns:
        The IDs of the deleted activities, so the caller can publish the cleanup
        events that reclaim each activity's thumbnail and stored source file.

    Raises:
        ProcessingError: On database error.
    """
    stmt = (
        sa_delete(activities_models.Activity)
        .where(
            activities_models.Activity.user_id == user_id,
            activities_models.Activity.strava_activity_id.isnot(None),
        )
        .returning(activities_models.Activity.id)
    )
    deleted_ids = [row_id for (row_id,) in db.execute(stmt).all()]
    if commit:
        db.commit()
    return deleted_ids


@core_decorators.handle_db_errors
def delete_all_activities_for_user(user_id: int, db: Session, commit: bool = True) -> list[int]:
    """Delete every activity owned by a user.

    Used by account deletion, which previously relied on the database FK cascade
    from ``users``. The cascade removes the rows but tells nobody, so each
    activity's thumbnail and stored source file were left behind — deleting them
    explicitly here yields the IDs needed to publish the cleanup events, making
    account deletion erase the user's stored artifacts too.

    Args:
        user_id: Owner user ID.
        db: Database session.
        commit: When True (default) commit immediately. Pass False to stage the
            deletes in the caller's unit of work.

    Returns:
        The IDs of the deleted activities.

    Raises:
        ProcessingError: On database error.
    """
    stmt = (
        sa_delete(activities_models.Activity)
        .where(activities_models.Activity.user_id == user_id)
        .returning(activities_models.Activity.id)
    )
    deleted_ids = [row_id for (row_id,) in db.execute(stmt).all()]
    if commit:
        db.commit()
    return deleted_ids
