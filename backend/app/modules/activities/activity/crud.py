"""CRUD operations for activities."""

from collections import defaultdict
from collections.abc import Sequence
from datetime import UTC, date, datetime
from typing import Any, cast

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
from sqlalchemy.orm import Session

import core.etag as core_etag
import core.exceptions as core_exceptions
import core.logger as core_logger
import core.pagination as core_pagination
import core.timezone as core_timezone
import modules.activities.activity.constants as activity_constants
import modules.activities.activity.contracts as activity_contracts
import modules.activities.activity.models as activity_models
import modules.activities.activity.query as activity_query
import modules.activities.activity.schema as activity_schema
import modules.activities.activity.serializers as activity_serializers

logger = core_logger.get_logger(__name__)

# Frontend sort keys resolved to their model columns. Derived from the single
# vocabulary in ``constants`` rather than restated, so a key the transport layer
# accepts always has an ordering here.
SORT_MAP: dict[str, tuple[Any, ...]] = {
    key: tuple(getattr(activity_models.Activity, name) for name in column_names)
    for key, column_names in activity_constants.ACTIVITY_SORT_FIELDS.items()
}

_DEFAULT_SORT_COLUMNS = SORT_MAP[activity_constants.DEFAULT_ACTIVITY_SORT_FIELD]

# Stands in for NULL in numeric sorts. Its sign follows the direction, so a NULL
# sorts after every real value both ascending and descending.
_NULL_SORT_SENTINEL = 999999

# Columns that need COALESCE-with-sentinel so NULLs sort last
_NUMERIC_SORT_COLUMNS = {
    activity_models.Activity.distance,
    activity_models.Activity.total_timer_time,
    activity_models.Activity.calories,
    activity_models.Activity.elevation_gain,
    activity_models.Activity.pace,
    activity_models.Activity.average_hr,
}

# Text columns coalesced to "" so an unset place name orders with the empty ones
# instead of wherever the backend happens to put NULL.
_TEXT_SORT_COLUMNS = {
    activity_models.Activity.country,
    activity_models.Activity.city,
    activity_models.Activity.town,
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
            ordered = func.coalesce(column, _NULL_SORT_SENTINEL if ascending else -_NULL_SORT_SENTINEL)
        elif column in _TEXT_SORT_COLUMNS:
            ordered = func.coalesce(column, "")
        else:
            ordered = column
        clauses.append(ordered.asc() if ascending else ordered.desc())
    return clauses


def _is_not_live_strava_api_activity():
    """Return the policy predicate excluding live Strava API data.

    Returns:
        The SQL predicate.
    """
    return activity_models.Activity.strava_activity_id.is_(None)


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
    visibility_conditions = [activity_models.Activity.visibility == activity_constants.ActivityVisibilityLevel.PUBLIC]
    if followee_ids:
        visibility_conditions.append(
            and_(
                activity_models.Activity.visibility == activity_constants.ActivityVisibilityLevel.FOLLOWERS,
                activity_models.Activity.user_id.in_(followee_ids),
            )
        )

    return and_(
        activity_models.Activity.is_hidden.is_(False),
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


def _apply_user_activity_filters(
    stmt,
    *,
    activity_type: int | None,
    start_date: date | None,
    end_date: date | None,
    name_search: str | None,
    user_is_owner: bool,
    followee_ids: Sequence[int] | None,
):
    """Apply the filters shared by the activity list, page and count queries.

    One definition, so a page and its total cannot disagree on what matched.

    Args:
        stmt: SQLAlchemy select statement.
        activity_type: Optional activity type filter.
        start_date: Optional inclusive start date filter.
        end_date: Optional inclusive end date filter.
        name_search: Optional case-insensitive name search.
        user_is_owner: Whether the requester owns all candidate rows.
        followee_ids: The requester's accepted-followee user ids, resolved by
            the caller.

    Returns:
        The filtered statement.
    """
    stmt = _apply_activity_visibility_filter(stmt, user_is_owner=user_is_owner, followee_ids=followee_ids)
    if activity_type:
        stmt = stmt.where(activity_models.Activity.activity_type == activity_type)
    # Date filters are evaluated in each activity's own timezone, so a
    # user filtering "1 May" gets their 1 May, not UTC's.
    stmt = stmt.where(*activity_query.local_date_range_conditions(start_date, end_date, end_exclusive=False))
    if name_search:
        stmt = stmt.where(activity_query.name_search_condition(name_search))
    return stmt


def get_all_activities(
    db: Session,
) -> list[activity_schema.ActivityRead]:
    """Return every activity in the database, serialized.

    Note:
        Loads all rows in memory. Intended for migration
        scripts only — do not call from request handlers.

    Args:
        db: Database session.

    Returns:
        The activity schemas, empty when there are none.
    """
    activities = db.execute(select(activity_models.Activity)).scalars().all()
    if not activities:
        return []
    return [activity_serializers.to_read_schema(a) for a in activities]


def get_all_activities_for_migration(
    db: Session,
) -> list[activity_contracts.ActivityMigrationRef]:
    """Return a lightweight reference for every activity (migration use only).

    Projects only the identity, owner, provider ids, and time bounds the
    data-backfill migrations read, so no ORM row leaves the CRUD layer.

    Args:
        db: Database session.

    Returns:
        A migration reference per activity, or an empty list when there are none.
    """
    activities = db.execute(select(activity_models.Activity)).scalars().all()
    return [
        activity_contracts.ActivityMigrationRef(
            id=activity.id,
            user_id=activity.user_id,
            start_time=activity.start_time,
            end_time=activity.end_time,
            strava_activity_id=activity.strava_activity_id,
            garminconnect_activity_id=activity.garminconnect_activity_id,
        )
        for activity in activities
    ]


def get_user_activities(
    user_id: int,
    db: Session,
    *,
    activity_type: int | None = None,
    start_date: date | None = None,
    end_date: date | None = None,
    name_search: str | None = None,
    user_is_owner: bool,
    followee_ids: Sequence[int] | None = None,
) -> list[activity_schema.ActivityRead]:
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
        The matching activity schemas, empty when there are none.
    """
    stmt = select(activity_models.Activity).where(activity_models.Activity.user_id == user_id)
    stmt = _apply_user_activity_filters(
        stmt,
        activity_type=activity_type,
        start_date=start_date,
        end_date=end_date,
        name_search=name_search,
        user_is_owner=user_is_owner,
        followee_ids=followee_ids,
    )
    stmt = stmt.order_by(desc(activity_models.Activity.start_time))

    activities = db.execute(stmt).scalars().all()
    if not activities:
        return []
    return activity_serializers.serialize_and_mask(
        list(activities),
        requester_user_id=user_id if user_is_owner else None,
        force_non_owner=not user_is_owner,
    )


def count_user_activities(
    user_id: int,
    db: Session,
    *,
    activity_type: int | None = None,
    start_date: date | None = None,
    end_date: date | None = None,
    name_search: str | None = None,
    user_is_owner: bool,
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
    """
    stmt = select(func.count()).select_from(activity_models.Activity).where(activity_models.Activity.user_id == user_id)
    stmt = _apply_user_activity_filters(
        stmt,
        activity_type=activity_type,
        start_date=start_date,
        end_date=end_date,
        name_search=name_search,
        user_is_owner=user_is_owner,
        followee_ids=followee_ids,
    )
    count = db.execute(stmt).scalar()
    return count or 0


def get_user_activities_by_user_id_and_garminconnect_gear_set(
    user_id: int, db: Session
) -> list[activity_schema.ActivityRead]:
    """Get activities for a user that have a Garmin gear ID.

    Args:
        user_id: Owner user ID.
        db: Database session.

    Returns:
        The matching activity schemas, empty when there are none.
    """
    stmt = (
        select(activity_models.Activity)
        .where(
            activity_models.Activity.user_id == user_id,
            activity_models.Activity.garminconnect_gear_id.isnot(None),
        )
        .order_by(desc(activity_models.Activity.start_time))
    )
    activities = db.execute(stmt).scalars().all()
    if not activities:
        return []
    return activity_serializers.serialize_and_mask(
        list(activities),
        requester_user_id=user_id,
    )


def get_user_activities_with_pagination(
    user_id: int,
    db: Session,
    *,
    page_number: int = 1,
    num_records: int = core_pagination.DEFAULT_NUM_RECORDS,
    activity_type: int | None = None,
    start_date: date | None = None,
    end_date: date | None = None,
    name_search: str | None = None,
    sort_by: str | None = None,
    sort_order: str | None = None,
    user_is_owner: bool,
    followee_ids: Sequence[int] | None = None,
) -> list[activity_schema.ActivityRead]:
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
        The matching activity schemas, empty when there are none.
    """
    stmt = select(activity_models.Activity).where(
        activity_models.Activity.user_id == user_id,
    )
    stmt = _apply_user_activity_filters(
        stmt,
        activity_type=activity_type,
        start_date=start_date,
        end_date=end_date,
        name_search=name_search,
        user_is_owner=user_is_owner,
        followee_ids=followee_ids,
    )

    stmt = stmt.order_by(*_sort_order_by(sort_by, sort_order))

    stmt = stmt.offset((page_number - 1) * num_records).limit(num_records)

    activities = db.execute(stmt).scalars().all()
    if not activities:
        return []
    return activity_serializers.serialize_and_mask(
        list(activities),
        requester_user_id=user_id if user_is_owner else None,
        force_non_owner=not user_is_owner,
    )


def get_distinct_activity_types_for_user(user_id: int, db: Session) -> dict[int, str]:
    """Map distinct activity types owned by a user to names.

    Args:
        user_id: Owner user ID.
        db: Database session.

    Returns:
        Dict of activity_type -> human readable name.
    """
    stmt = (
        select(activity_models.Activity.activity_type)
        .where(activity_models.Activity.user_id == user_id)
        .distinct()
        .order_by(activity_models.Activity.activity_type)
    )
    type_ids = db.execute(stmt).scalars().all()
    return {
        type_id: activity_constants.ACTIVITY_ID_TO_NAME.get(type_id, "Unknown")
        for type_id in type_ids
        if type_id is not None
    }


def get_user_activities_per_timeframe(
    user_id: int,
    start: datetime,
    end: datetime,
    db: Session,
    *,
    user_is_owner: bool,
    followee_ids: Sequence[int] | None = None,
) -> list[activity_schema.ActivityRead]:
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
        The matching activity schemas, empty when there are none.
    """
    stmt = (
        select(activity_models.Activity)
        .where(
            activity_models.Activity.user_id == user_id,
            *activity_query.local_date_range_conditions(start.date(), end.date(), end_exclusive=False),
        )
        .order_by(desc(activity_models.Activity.start_time))
    )
    stmt = _apply_activity_visibility_filter(
        stmt,
        user_is_owner=user_is_owner,
        followee_ids=followee_ids,
    )
    activities = db.execute(stmt).scalars().all()
    if not activities:
        return []
    return activity_serializers.serialize_and_mask(
        list(activities),
        requester_user_id=user_id if user_is_owner else None,
        force_non_owner=not user_is_owner,
    )


def get_user_activities_per_timeframe_and_activity_types(
    user_id: int,
    activity_types: list[int],
    start: datetime,
    end: datetime,
    db: Session,
    *,
    user_is_owner: bool,
    followee_ids: Sequence[int] | None = None,
    exclude_hidden: bool = False,
) -> list[activity_schema.ActivityRead]:
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
    """
    stmt = (
        select(activity_models.Activity)
        .where(
            activity_models.Activity.user_id == user_id,
            activity_models.Activity.activity_type.in_(activity_types),
            *activity_query.local_date_range_conditions(start.date(), end.date(), end_exclusive=False),
        )
        .order_by(desc(activity_models.Activity.start_time))
    )
    if exclude_hidden:
        stmt = stmt.where(activity_models.Activity.is_hidden.is_(False))
    stmt = _apply_activity_visibility_filter(
        stmt,
        user_is_owner=user_is_owner,
        followee_ids=followee_ids,
    )
    activities = db.execute(stmt).scalars().all()
    if not activities:
        return []
    return activity_serializers.serialize_and_mask(
        list(activities),
        requester_user_id=user_id if user_is_owner else None,
        force_non_owner=not user_is_owner,
    )


def get_following_feed_after(
    followee_ids: list[int],
    after: tuple[datetime, int] | None,
    num_records: int,
    db: Session,
) -> list[activity_contracts.ActivityFeedEntry]:
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
    stmt = select(activity_models.Activity).where(
        activity_models.Activity.user_id.in_(followee_ids),
        activity_models.Activity.visibility.in_([0, 1]),
        activity_models.Activity.is_hidden.is_(False),
        _is_not_live_strava_api_activity(),
    )
    if after is not None:
        last_start_time, last_id = after
        # Row-value comparison: strictly older, or same instant with a lower id.
        stmt = stmt.where(
            tuple_(activity_models.Activity.start_time, activity_models.Activity.id)
            < tuple_(literal(last_start_time), literal(last_id))
        )
    stmt = stmt.order_by(desc(activity_models.Activity.start_time), desc(activity_models.Activity.id)).limit(
        num_records
    )
    activities = db.execute(stmt).scalars().all()
    if not activities:
        return []
    masked = activity_serializers.serialize_and_mask(list(activities), force_non_owner=True)
    return [
        activity_contracts.ActivityFeedEntry(
            activity=item,
            cursor_start_time=orm_activity.start_time,
            cursor_id=orm_activity.id,
        )
        for orm_activity, item in zip(activities, masked, strict=True)
    ]


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
    """
    stmt = (
        select(func.count())
        .select_from(activity_models.Activity)
        .where(
            activity_models.Activity.user_id == user_id,
            activity_models.Activity.gear_id == gear_id,
        )
    )
    count = db.execute(stmt).scalar()
    return count or 0


def get_user_activities_by_gear_id_and_user_id(
    user_id: int, gear_id: int, db: Session
) -> list[activity_schema.ActivityRead]:
    """Get all activities for a gear owned by a user.

    Args:
        user_id: Owner user ID.
        gear_id: Gear ID.
        db: Database session.

    Returns:
        The matching activity schemas, empty when there are none.
    """
    stmt = (
        select(activity_models.Activity)
        .where(
            activity_models.Activity.user_id == user_id,
            activity_models.Activity.gear_id == gear_id,
        )
        .order_by(desc(activity_models.Activity.start_time))
    )
    activities = db.execute(stmt).scalars().all()
    if not activities:
        return []
    return activity_serializers.serialize_and_mask(
        list(activities),
        requester_user_id=user_id,
    )


def get_user_activities_by_gear_id_and_user_id_with_pagination(
    user_id: int,
    gear_id: int,
    page_number: int,
    num_records: int,
    db: Session,
) -> list[activity_schema.ActivityRead]:
    """Get a page of activities for a gear owned by a user.

    Args:
        user_id: Owner user ID.
        gear_id: Gear ID.
        page_number: 1-based page number.
        num_records: Records per page.
        db: Database session.

    Returns:
        The matching activity schemas, empty when there are none.
    """
    stmt = (
        select(activity_models.Activity)
        .where(
            activity_models.Activity.user_id == user_id,
            activity_models.Activity.gear_id == gear_id,
        )
        .order_by(desc(activity_models.Activity.start_time))
        .offset((page_number - 1) * num_records)
        .limit(num_records)
    )
    activities = db.execute(stmt).scalars().all()
    if not activities:
        return []
    return activity_serializers.serialize_and_mask(
        list(activities),
        requester_user_id=user_id,
    )


def sum_gear_usage(gear_id: int, user_id: int, db: Session) -> activity_contracts.ActivityUsageTotals:
    """Total distance and moving time a user recorded against a gear.

    Lives here rather than in the gears module so the activities table is only
    ever queried by its owner. Only the gear owner's own activities count, so an
    activity another user linked to this gear never inflates its totals.

    Args:
        gear_id: The gear to accumulate usage for.
        user_id: The gear's owner.
        db: Database session.

    Returns:
        The gear's totals; zeroes when it has no activities.
    """
    stmt = select(
        func.coalesce(func.sum(activity_models.Activity.distance), 0),
        func.coalesce(func.sum(activity_models.Activity.total_timer_time), 0),
    ).where(activity_models.Activity.gear_id == gear_id, activity_models.Activity.user_id == user_id)
    distance, moving_time = db.execute(stmt).one()
    return activity_contracts.ActivityUsageTotals(distance=float(distance), time=float(moving_time))


def sum_gear_usage_by_window(
    gear_id: int,
    user_id: int,
    windows: Sequence[activity_contracts.GearUsageWindow],
    db: Session,
) -> dict[int, activity_contracts.ActivityUsageTotals]:
    """Total distance and moving time per date window for one gear.

    Answers "how far has each component of this gear been ridden?" in a single
    pass over the gear's activities: each window contributes a pair of conditional
    sums, so adding a component costs two more aggregate expressions rather than
    another round trip. Windows are matched against each activity's **local** date
    (see :class:`~modules.activities.activity.contracts.GearUsageWindow`).

    Only the gear owner's own activities count, as in :func:`sum_gear_usage`.

    Args:
        gear_id: The gear whose activities to accumulate.
        user_id: The gear's owner.
        windows: The date windows to accumulate over, keyed by the caller.
        db: Database session.

    Returns:
        Totals per window key. Windows with no matching activity report zeroes,
        so every requested key is always present.
    """
    if not windows:
        return {}

    local_date = func.date(activity_query.local_start_time_expression())

    columns = []
    for window in windows:
        in_window = local_date >= window.start_date
        if window.end_date is not None:
            in_window = and_(in_window, local_date <= window.end_date)
        columns.append(func.coalesce(func.sum(case((in_window, activity_models.Activity.distance), else_=0)), 0))
        columns.append(
            func.coalesce(func.sum(case((in_window, activity_models.Activity.total_timer_time), else_=0)), 0)
        )

    stmt = select(*columns).where(
        activity_models.Activity.gear_id == gear_id, activity_models.Activity.user_id == user_id
    )
    row = db.execute(stmt).one()

    return {
        window.key: activity_contracts.ActivityUsageTotals(
            distance=float(row[index * 2]),
            time=float(row[index * 2 + 1]),
        )
        for index, window in enumerate(windows)
    }


def get_activity_by_id_from_user_id_or_has_visibility(
    activity_id: int, user_id: int, db: Session, *, followee_ids: Sequence[int] | None = None
) -> activity_schema.ActivityRead | None:
    """Get an activity by ID if owned or visible to the user.

    Args:
        activity_id: Activity ID.
        user_id: Requesting user ID.
        db: Database session.
        followee_ids: The requester's accepted-followee user ids, resolved by
            the caller.

    Returns:
        Activity schema or None if not found / not visible.
    """
    stmt = select(activity_models.Activity).where(
        or_(
            activity_models.Activity.user_id == user_id,
            _visible_to_requester_condition(followee_ids),
        ),
        activity_models.Activity.id == activity_id,
    )
    activity = db.execute(stmt).scalar_one_or_none()
    if not activity:
        return None
    schema = activity_serializers.to_read_schema(activity)
    is_owner = activity.user_id == user_id
    activity_serializers.apply_visibility_mask(schema, is_owner=is_owner)
    return schema


def get_viewable_activity_by_id_for_user(
    activity_id: int, user_id: int, db: Session, *, followee_ids: Sequence[int] | None = None
) -> activity_schema.ActivityRead | None:
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
    """
    stmt = select(activity_models.Activity).where(
        or_(
            activity_models.Activity.user_id == user_id,
            _visible_to_requester_condition(followee_ids),
        ),
        activity_models.Activity.id == activity_id,
    )
    activity = db.execute(stmt).scalar_one_or_none()
    if not activity:
        return None
    return activity_serializers.to_read_schema(activity)


def get_activity_by_id_if_is_public(activity_id: int, db: Session) -> activity_schema.ActivityRead | None:
    """Get an activity by ID if it is publicly shareable.

    Answers only the row-level question. Whether the server allows public
    shareable links at all is a policy the caller checks first — asking another
    module mid-``SELECT`` is a service decision, not a persistence one.

    Args:
        activity_id: Activity ID.
        db: Database session.

    Returns:
        Activity schema or None when not public / not found.
    """
    stmt = select(activity_models.Activity).where(
        activity_models.Activity.visibility == activity_constants.ActivityVisibilityLevel.PUBLIC,
        activity_models.Activity.is_hidden.is_(False),
        _is_not_live_strava_api_activity(),
        activity_models.Activity.id == activity_id,
    )
    activity = db.execute(stmt).scalar_one_or_none()
    if not activity:
        return None
    schema = activity_serializers.to_read_schema(activity)
    activity_serializers.apply_visibility_mask(schema, is_owner=False)
    return schema


def get_public_activity_for_child_read(
    activity_id: int,
    db: Session,
    *,
    hide_attr: str,
) -> activity_schema.ActivityRead | None:
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

    The ``is_hidden`` check is part of step 1 so a hidden (duplicate-start-time)
    activity does not serve its laps, sets and workout steps to anonymous callers
    (OWASP A01: broken access control). Routing every child through this one
    function keeps that rule from diverging by copy-paste.

    Args:
        activity_id: Activity ID being read.
        db: Database session.
        hide_attr: Name of the boolean ``hide_*`` attribute on the activity
            schema that gates this child resource.

    Returns:
        The public activity schema when the child rows may be served anonymously,
        otherwise ``None``.
    """
    activity = get_activity_by_id_if_is_public(activity_id, db)
    if activity is None:
        return None

    if getattr(activity, hide_attr):
        return None

    return activity


def get_existing_activity_ids(activity_ids: Sequence[int], db: Session) -> set[int]:
    """Return which of the given activity IDs still have a row.

    Args:
        activity_ids: The IDs to look up.
        db: Database session.

    Returns:
        The subset of ``activity_ids`` that exist.
    """
    if not activity_ids:
        return set()
    stmt = select(activity_models.Activity.id).where(activity_models.Activity.id.in_(activity_ids))
    return set(db.scalars(stmt).all())


def get_activity_by_id(activity_id: int, db: Session) -> activity_schema.ActivityRead | None:
    """Get an activity by ID without permission checks.

    Args:
        activity_id: Activity ID.
        db: Database session.

    Returns:
        Activity schema or None when not found.
    """
    stmt = select(activity_models.Activity).where(
        activity_models.Activity.id == activity_id,
    )
    activity = db.execute(stmt).scalar_one_or_none()
    if not activity:
        return None
    return activity_serializers.to_read_schema(activity)


def get_activity_by_start_time(
    start_time: str | datetime, user_id: int, db: Session
) -> activity_schema.ActivityRead | None:
    """Get a user's activity matching a specific start time.

    Args:
        start_time: ISO-format string or datetime.
        user_id: Owner user ID.
        db: Database session.

    Returns:
        Activity schema or None when not found.
    """
    if isinstance(start_time, str):
        start_time = datetime.fromisoformat(start_time)
    if start_time.tzinfo is None:
        start_time = start_time.replace(tzinfo=UTC)
    # ``first`` rather than ``scalar_one_or_none``: a start-time duplicate is
    # stored (hidden), not rejected, so several rows can share the instant and
    # the lookup would otherwise raise on the third import.
    stmt = (
        select(activity_models.Activity)
        .where(
            activity_models.Activity.user_id == user_id,
            activity_models.Activity.start_time == start_time,
        )
        .order_by(activity_models.Activity.id)
    )
    activity = db.scalars(stmt).first()
    if not activity:
        return None
    return activity_serializers.to_read_schema(activity)


def get_activity_by_dedup_key(dedup_key: str, user_id: int, db: Session) -> activity_schema.ActivityRead | None:
    """Get a user's activity by its idempotency dedup key.

    Used by the ingestion seam to make re-import of an already-ingested activity
    a no-op: a provider-scoped id now, a content hash later.

    Args:
        dedup_key: Stable idempotency key (e.g. ``"strava:123"``).
        user_id: Owner user ID.
        db: Database session.

    Returns:
        Activity schema or None when not found.
    """
    stmt = select(activity_models.Activity).where(
        activity_models.Activity.user_id == user_id,
        activity_models.Activity.dedup_key == dedup_key,
    )
    activity = db.execute(stmt).scalars().first()
    if not activity:
        return None
    return activity_serializers.to_read_schema(activity)


def get_activity_by_id_from_user_id(activity_id: int, user_id: int, db: Session) -> activity_schema.ActivityRead | None:
    """Get a user's activity by ID.

    Args:
        activity_id: Activity ID.
        user_id: Owner user ID.
        db: Database session.

    Returns:
        Activity schema or None when not found.
    """
    stmt = select(activity_models.Activity).where(
        activity_models.Activity.user_id == user_id,
        activity_models.Activity.id == activity_id,
    )
    activity = db.execute(stmt).scalar_one_or_none()
    if not activity:
        return None
    return activity_serializers.to_read_schema(activity)


def get_activity_by_strava_id_from_user_id(
    activity_strava_id: int, user_id: int, db: Session
) -> activity_schema.ActivityRead | None:
    """Get a user's activity by its Strava activity ID.

    Args:
        activity_strava_id: Strava activity ID.
        user_id: Owner user ID.
        db: Database session.

    Returns:
        Activity schema or None when not found.
    """
    stmt = select(activity_models.Activity).where(
        activity_models.Activity.user_id == user_id,
        activity_models.Activity.strava_activity_id == activity_strava_id,
    )
    activity = db.execute(stmt).scalar_one_or_none()
    if not activity:
        return None
    return activity_serializers.to_read_schema(activity)


def get_activity_by_garminconnect_id_from_user_id(
    activity_garminconnect_id: int, user_id: int, db: Session
) -> activity_schema.ActivityRead | None:
    """Get a user's activity by its Garmin Connect activity ID.

    Args:
        activity_garminconnect_id: Garmin Connect activity ID.
        user_id: Owner user ID.
        db: Database session.

    Returns:
        Activity schema or None when not found.
    """
    stmt = select(activity_models.Activity).where(
        activity_models.Activity.user_id == user_id,
        activity_models.Activity.garminconnect_activity_id == activity_garminconnect_id,
    )
    activity = db.execute(stmt).scalars().first()
    if not activity:
        return None
    return activity_serializers.to_read_schema(activity)


def create_activity(
    activity: activity_contracts.ActivityCore,
    db: Session,
    *,
    dedup_key: str | None = None,
) -> activity_schema.ActivityRead:
    """Stage a new activity; duplicate start-times are marked hidden.

    Pure persistence: notifications and derived work (thumbnails, HR zones) are
    decoupled to ``activity.created`` subscribers. The caller publishes
    the event after the activity's children are stored; this function only stages
    the row (flushed, not committed) and flags start-time duplicates as hidden.

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

    # Best-effort: this check and the insert below are not atomic, so two concurrent
    # imports with the same start time can both stay visible. Idempotency does not
    # rest on it; ``dedup_key`` and its unique index do.
    activity_start_time_exists = get_activity_by_start_time(normalized_start_time, activity.user_id, db)

    new_activity = activity_serializers.to_orm(activity)
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
    # Flush so the generated id / created_at are available. The caller owns the
    # commit, so the whole unit of work (activity + children + outbox row) is
    # one transaction.
    db.flush()
    db.refresh(new_activity)

    # Build the read schema from the stored row. Returning a freshly serialized
    # ``Activity`` (rather than handing back the mutated input) is what makes the
    # declared ``ActivityCore -> Activity`` signature true: the generated id and
    # ``created_at`` belong to the read model, which the ingestion contract
    # deliberately does not carry.
    created = activity_serializers.to_read_schema(new_activity)

    return created


def set_activity_thumbnail_key(
    activity_id: int,
    thumbnail_path: str | None,
    db: Session,
    *,
    expected_key: str | None = None,
) -> bool:
    """Stage the map thumbnail path for an activity.

    A derived value, so it is written with a Core ``UPDATE`` that leaves ``version``
    alone: a background render must not invalidate the ETag of a user who is
    mid-edit.

    Args:
        activity_id: Target activity ID.
        thumbnail_path: Absolute path to the thumbnail file.
        db: Database session.
        expected_key: When given, write only if the activity still holds this key, so a
            reconciliation pass never overwrites a key stored after it read the row.

    Returns:
        True when the activity exists (and holds ``expected_key`` when given) and was
        updated, False otherwise.
    """
    stmt = sa_update(activity_models.Activity).where(activity_models.Activity.id == activity_id)
    if expected_key is not None:
        stmt = stmt.where(activity_models.Activity.map_thumbnail_path == expected_key)
    result = cast("CursorResult[Any]", db.execute(stmt.values(map_thumbnail_path=thumbnail_path)))
    db.flush()
    if result.rowcount == 0:
        logger.warning(
            "Activity not found when setting the thumbnail path",
            extra=core_logger.context(activity_id=activity_id),
        )
        return False
    return True


def update_activity_location(
    activity_id: int,
    city: str | None,
    town: str | None,
    country: str | None,
    db: Session,
) -> bool:
    """Stage a reverse-geocoded location on an activity that has none yet.

    Written by the geocoding subscriber / backfill once the location for a GPS
    activity has been resolved. The geocoder is a slow network call made after the
    activity was read, so the write is conditional on the location still being
    unset: a concurrent replica's lookup or a user's edit is never overwritten.

    Args:
        activity_id: Target activity ID.
        city: Resolved city, or None.
        town: Resolved town, or None.
        country: Resolved country, or None.
        db: Database session.

    Returns:
        True when the location was written, False when the activity was not found
        or already has a location.
    """
    result = cast(
        "CursorResult[Any]",
        db.execute(
            sa_update(activity_models.Activity)
            .where(
                activity_models.Activity.id == activity_id,
                activity_models.Activity.city.is_(None),
                activity_models.Activity.town.is_(None),
                activity_models.Activity.country.is_(None),
            )
            .values(city=city, town=town, country=country)
        ),
    )
    db.flush()
    return result.rowcount == 1


def get_activities_missing_location(
    db: Session,
    *,
    due_at: datetime,
    after_id: int = 0,
    limit: int = core_pagination.DEFAULT_EXTERNAL_IO_BATCH_SIZE,
) -> list[activity_contracts.ActivityLocationRef]:
    """Return references to activities whose location is unresolved and due a lookup.

    Rows where ``city``, ``town`` and ``country`` are all NULL and whose
    ``location_next_lookup_at`` is unset or not after ``due_at`` — candidates for
    the reverse-geocoding backfill. Ordered by id and paged via ``after_id``.

    Args:
        db: Database session.
        due_at: Only rows due at or before this instant are returned.
        after_id: Return only activities with ``id`` greater than this.
        limit: Maximum number of candidate rows to return.

    Returns:
        Location references (id only) ordered by id.
    """
    stmt = (
        select(activity_models.Activity.id)
        .where(
            activity_models.Activity.city.is_(None),
            activity_models.Activity.town.is_(None),
            activity_models.Activity.country.is_(None),
            or_(
                activity_models.Activity.location_next_lookup_at.is_(None),
                activity_models.Activity.location_next_lookup_at <= due_at,
            ),
            activity_models.Activity.id > after_id,
        )
        .order_by(activity_models.Activity.id)
        .limit(limit)
    )
    ids = db.execute(stmt).scalars().all()
    return [activity_contracts.ActivityLocationRef(id=activity_id) for activity_id in ids]


def defer_location_lookups(activity_ids: Sequence[int], retry_at: datetime, db: Session) -> None:
    """Stage the next lookup time for activities whose location did not resolve.

    Args:
        activity_ids: Activities to defer.
        retry_at: Earliest time the backfill may look them up again.
        db: Database session.
    """
    if not activity_ids:
        return
    db.execute(
        sa_update(activity_models.Activity)
        .where(activity_models.Activity.id.in_(activity_ids))
        .values(location_next_lookup_at=retry_at)
    )
    db.flush()


def clear_all_activity_thumbnail_keys(db: Session) -> None:
    """Stage ``map_thumbnail_path`` = NULL on every activity.

    Args:
        db: Database session.
    """
    # The deferral goes too: clearing keys is a request to render everything now,
    # and a changed tile server is the usual cure for the failures it recorded.
    db.execute(sa_update(activity_models.Activity).values(map_thumbnail_path=None, thumbnail_next_attempt_at=None))


def get_activities_with_thumbnail(
    db: Session,
    *,
    after_id: int = 0,
    limit: int = core_pagination.DEFAULT_MAINTENANCE_BATCH_SIZE,
) -> list[activity_contracts.ActivityThumbnailRef]:
    """Return references to activities that have a map thumbnail.

    Ordered by id and paged via ``after_id`` so the thumbnail reconciliation pass
    walks the table in bounded batches instead of materialising every row.

    Args:
        db: Database session.
        after_id: Return only activities with ``id`` greater than this.
        limit: Maximum number of rows to return.

    Returns:
        Thumbnail references (id + stored key) for rows with
        ``map_thumbnail_path`` set.
    """
    stmt = (
        select(activity_models.Activity.id, activity_models.Activity.map_thumbnail_path)
        .where(
            activity_models.Activity.map_thumbnail_path.isnot(None),
            activity_models.Activity.id > after_id,
        )
        .order_by(activity_models.Activity.id)
        .limit(limit)
    )
    return [
        activity_contracts.ActivityThumbnailRef(id=row.id, map_thumbnail_path=row.map_thumbnail_path)
        for row in db.execute(stmt)
    ]


def get_activities_without_thumbnail(
    db: Session,
    *,
    due_at: datetime,
    after_id: int = 0,
    limit: int = core_pagination.DEFAULT_MAINTENANCE_BATCH_SIZE,
) -> list[activity_contracts.ActivityThumbnailRef]:
    """Return references to activities that have no map thumbnail and are due an attempt.

    Ordered by id and paged via ``after_id``. The caller advances the cursor
    rather than re-reading from zero: a batch whose thumbnails all fail to render
    still has to be stepped over, or the pass loops on it forever.

    Args:
        db: Database session.
        due_at: Only rows not deferred past this instant are returned.
        after_id: Return only activities with ``id`` greater than this.
        limit: Maximum number of rows to return.

    Returns:
        Thumbnail references (id, with a null key) for rows with
        ``map_thumbnail_path`` set to NULL.
    """
    stmt = (
        select(activity_models.Activity.id, activity_models.Activity.map_thumbnail_path)
        .where(
            activity_models.Activity.map_thumbnail_path.is_(None),
            or_(
                activity_models.Activity.thumbnail_next_attempt_at.is_(None),
                activity_models.Activity.thumbnail_next_attempt_at <= due_at,
            ),
            activity_models.Activity.id > after_id,
        )
        .order_by(activity_models.Activity.id)
        .limit(limit)
    )
    return [
        activity_contracts.ActivityThumbnailRef(id=row.id, map_thumbnail_path=row.map_thumbnail_path)
        for row in db.execute(stmt)
    ]


def defer_thumbnail_attempts(activity_ids: Sequence[int], retry_at: datetime, db: Session) -> None:
    """Stage the next attempt time for activities that did not get a thumbnail.

    Args:
        activity_ids: Activities to defer.
        retry_at: Earliest time the backfill may try them again.
        db: Database session.
    """
    if not activity_ids:
        return
    db.execute(
        sa_update(activity_models.Activity)
        .where(activity_models.Activity.id.in_(activity_ids))
        .values(thumbnail_next_attempt_at=retry_at)
    )
    db.flush()


def get_activities_with_legacy_thumbnail_path(
    db: Session,
    *,
    after_id: int = 0,
    limit: int = core_pagination.DEFAULT_EXTERNAL_IO_BATCH_SIZE,
) -> list[activity_contracts.ActivityThumbnailRef]:
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
        path.
    """
    stmt = (
        select(activity_models.Activity)
        .where(
            activity_models.Activity.map_thumbnail_path.isnot(None),
            activity_models.Activity.map_thumbnail_path.like("%/%"),
            activity_models.Activity.id > after_id,
        )
        .order_by(activity_models.Activity.id)
        .limit(limit)
    )
    rows = db.execute(stmt).scalars().all()
    return [
        activity_contracts.ActivityThumbnailRef(id=row.id, map_thumbnail_path=row.map_thumbnail_path) for row in rows
    ]


def edit_activity(
    user_id: int,
    activity_id: int,
    activity_attributes: activity_schema.ActivityEdit | activity_schema.ActivityRead,
    db: Session,
    *,
    if_match: str | None = None,
) -> activity_schema.ActivityRead:
    """Stage partial updates to a user's activity.

    Args:
        user_id: Owner user ID.
        activity_id: ID of the activity to update (from the request path).
        activity_attributes: Pydantic model carrying the fields to update;
            only the fields explicitly set are applied.
        db: Database session.
        if_match: The ``If-Match`` precondition, or None. Checked against the very
            row this function edits, so the version it compares is the version the
            flush's ``version_id_col`` guard then holds the write to.

    Returns:
        The updated activity as a serialized schema.

    Raises:
        NotFoundError: When the activity is missing.
        PreconditionFailedError: When ``if_match`` does not name the row's version.
    """
    stmt = select(activity_models.Activity).where(
        activity_models.Activity.user_id == user_id,
        activity_models.Activity.id == activity_id,
    )
    db_activity = db.execute(stmt).scalar_one_or_none()
    if db_activity is None:
        raise core_exceptions.NotFoundError("Activity not found")
    core_etag.require_if_match(if_match, db_activity.version)

    for key, value in activity_serializers.to_update_values(activity_attributes).items():
        setattr(db_activity, key, value)

    # The version bump lives in the ORM's UPDATE, so flush before reading it
    # back — the caller serializes this row into its response and would
    # otherwise hand out a stale ETag.
    db.flush()
    db.refresh(db_activity)
    return activity_serializers.to_read_schema(db_activity)


def _lock_user_activities(user_id: int, db: Session, activity_ids: Sequence[int] | None = None) -> None:
    """Row-lock a user's activities in id order before a multi-row ``UPDATE``.

    A multi-row ``UPDATE`` locks rows in scan order, so two overlapping bulk
    writes can each hold a row the other wants and deadlock. Taking every lock in
    id order first makes the later ``UPDATE``s wait their turn instead.

    Args:
        user_id: Owner user ID.
        db: Database session.
        activity_ids: Restrict the lock to these activities, or lock them all.
    """
    stmt = select(activity_models.Activity.id).where(activity_models.Activity.user_id == user_id)
    if activity_ids is not None:
        stmt = stmt.where(activity_models.Activity.id.in_(activity_ids))
    db.execute(stmt.order_by(activity_models.Activity.id).with_for_update())


def edit_user_activities_visibility(user_id: int, visibility: int, db: Session) -> list[int]:
    """Stage a bulk visibility update for every activity of a user.

    Args:
        user_id: Owner user ID.
        visibility: New visibility value (0, 1, 2).
        db: Database session.

    Returns:
        The IDs of the updated activities, so the caller can publish one event
        per row instead of re-deriving which activities the user owns.
    """
    _lock_user_activities(user_id, db)
    stmt = (
        sa_update(activity_models.Activity)
        .where(activity_models.Activity.user_id == user_id)
        # Core UPDATEs bypass the ORM version bump, so an ETag would survive a
        # change it should have invalidated.
        .values(visibility=visibility, version=activity_models.Activity.version + 1)
        .returning(activity_models.Activity.id)
    )
    return [row_id for (row_id,) in db.execute(stmt).all()]


def bulk_set_activities_gear_id(
    user_id: int,
    gear_assignments: dict[int, int | None],
    db: Session,
) -> list[int]:
    """Stage a bulk ``gear_id`` update for many activities owned by a user.

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

    Returns:
        The IDs of the activities actually updated — a subset of the requested
        keys, since the ownership predicate silently drops another user's ids.
    """
    if not gear_assignments:
        return []
    _lock_user_activities(user_id, db, list(gear_assignments))
    by_gear: dict[int | None, list[int]] = defaultdict(list)
    for activity_id, gear_id in gear_assignments.items():
        by_gear[gear_id].append(activity_id)

    updated_ids: list[int] = []
    for gear_id, activity_ids in by_gear.items():
        stmt = (
            sa_update(activity_models.Activity)
            .where(
                activity_models.Activity.user_id == user_id,
                activity_models.Activity.id.in_(activity_ids),
            )
            .values(gear_id=gear_id, version=activity_models.Activity.version + 1)
            .returning(activity_models.Activity.id)
        )
        updated_ids.extend(row_id for (row_id,) in db.execute(stmt).all())
    return updated_ids


def delete_activity(activity_id: int, user_id: int, db: Session) -> None:
    """Stage the deletion of an activity owned by ``user_id``.

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

    Raises:
        NotFoundError: When the activity is missing or not owned by ``user_id``.
    """
    stmt = sa_delete(activity_models.Activity).where(
        activity_models.Activity.id == activity_id,
        activity_models.Activity.user_id == user_id,
    )
    result = cast("CursorResult[Any]", db.execute(stmt))
    if result.rowcount == 0:
        # Nothing matched, so nothing was staged; the 404 needs no rollback.
        raise core_exceptions.NotFoundError(f"Activity with id {activity_id} not found")


def delete_all_strava_activities_for_user(user_id: int, db: Session) -> list[int]:
    """Stage the deletion of every Strava-synced activity owned by a user.

    Args:
        user_id: Owner user ID.
        db: Database session.

    Returns:
        The IDs of the deleted activities, so the caller can publish the cleanup
        events that reclaim each activity's thumbnail and stored source file.
    """
    _lock_user_activities(user_id, db)
    stmt = (
        sa_delete(activity_models.Activity)
        .where(
            activity_models.Activity.user_id == user_id,
            activity_models.Activity.strava_activity_id.isnot(None),
        )
        .returning(activity_models.Activity.id)
    )
    return [row_id for (row_id,) in db.execute(stmt).all()]


def delete_all_activities_for_user(user_id: int, db: Session) -> list[int]:
    """Stage the deletion of every activity owned by a user.

    Used by account deletion. The database FK cascade from ``users`` would remove
    the rows but tell nobody, leaving each activity's thumbnail and stored source
    file behind — deleting them explicitly here yields the IDs needed to publish
    the cleanup events, so account deletion erases the user's stored artifacts too.

    Args:
        user_id: Owner user ID.
        db: Database session.

    Returns:
        The IDs of the deleted activities.
    """
    _lock_user_activities(user_id, db)
    stmt = (
        sa_delete(activity_models.Activity)
        .where(activity_models.Activity.user_id == user_id)
        .returning(activity_models.Activity.id)
    )
    return [row_id for (row_id,) in db.execute(stmt).all()]
