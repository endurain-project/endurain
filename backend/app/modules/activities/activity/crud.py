"""CRUD operations for activities."""

from collections import defaultdict
from datetime import UTC, date, datetime
from typing import Any, cast
from urllib.parse import unquote

from fastapi import HTTPException, status
from pydantic import BaseModel
from sqlalchemy import (
    CursorResult,
    and_,
    desc,
    func,
    or_,
    select,
)
from sqlalchemy import (
    delete as sa_delete,
)
from sqlalchemy import (
    update as sa_update,
)
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

import core.logger as core_logger
import core.sanitization as core_sanitization
import core.timezone as core_timezone
import modules.activities.activity.constants as activities_constants
import modules.activities.activity.models as activities_models
import modules.activities.activity.schema as activities_schema
import modules.activities.activity.serializers as activities_serializers
import modules.followers.service as followers_service
import modules.server_settings.utils as server_settings_utils

# Mapping from frontend sort keys to model columns
SORT_MAP = {
    "type": activities_models.Activity.activity_type,
    "name": activities_models.Activity.name,
    "start_time": activities_models.Activity.start_time,
    "duration": activities_models.Activity.total_timer_time,
    "distance": activities_models.Activity.distance,
    "calories": activities_models.Activity.calories,
    "elevation": activities_models.Activity.elevation_gain,
    "pace": activities_models.Activity.pace,
    "average_hr": activities_models.Activity.average_hr,
}

# Columns that need COALESCE-with-sentinel so NULLs sort last
_NUMERIC_SORT_COLUMNS = {
    activities_models.Activity.distance,
    activities_models.Activity.total_timer_time,
    activities_models.Activity.calories,
    activities_models.Activity.elevation_gain,
    activities_models.Activity.pace,
    activities_models.Activity.average_hr,
}


def escape_like(term: str) -> str:
    """Escape SQL LIKE wildcards in a user-provided term.

    Escapes ``\\``, ``%`` and ``_`` so they are matched literally. Use together
    with ``.like(..., escape="\\\\")`` to keep user input from injecting LIKE
    wildcards into search filters.

    Args:
        term: Raw search term.

    Returns:
        Escaped search term safe for use inside a ``LIKE`` pattern.
    """
    return term.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def _visible_to_requester_condition(requester_user_id: int | None, db: Session):
    """Build the non-owner activity visibility condition.

    Args:
        requester_user_id: Requesting user ID, or None for an
            anonymous/public-only read.
        db: Database session, used to resolve the requester's accepted
            followees through the followers service interface.

    Returns:
        SQLAlchemy condition limiting rows to public or accepted
        follower-visible activities.
    """
    visibility_conditions = [activities_models.Activity.visibility == 0]
    if requester_user_id is not None:
        followee_ids = followers_service.list_accepted_followee_ids(requester_user_id, db)
        if followee_ids:
            visibility_conditions.append(
                and_(
                    activities_models.Activity.visibility == 1,
                    activities_models.Activity.user_id.in_(followee_ids),
                )
            )

    return and_(
        activities_models.Activity.is_hidden.is_(False),
        or_(*visibility_conditions),
    )


def _apply_activity_visibility_filter(
    stmt,
    *,
    user_is_owner: bool,
    requester_user_id: int | None,
    db: Session,
):
    """Apply non-owner visibility filtering to an activity query.

    Args:
        stmt: SQLAlchemy select statement.
        user_is_owner: Whether the requester owns all candidate
            rows.
        requester_user_id: Requesting user ID for follower checks.
        db: Database session, used to resolve the requester's accepted
            followees through the followers service interface.

    Returns:
        The original statement for owner reads, otherwise a
        filtered statement.
    """
    if user_is_owner:
        return stmt
    return stmt.where(_visible_to_requester_condition(requester_user_id, db))


def _internal_server_error(err: Exception, context: str) -> HTTPException:
    """Build a logged HTTP 500 error from an exception.

    Args:
        err: The original exception.
        context: Function name used in the log message.

    Returns:
        HTTPException with a 500 status code.
    """
    core_logger.print_to_log(f"Error in {context}: {err}", "error", exc=err)
    return HTTPException(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        detail="Internal Server Error",
    )


def _transform_schema_activity_to_model_activity(
    activity: activities_schema.Activity,
) -> activities_models.Activity:
    # Use an explicit UTC-aware created_at when provided,
    # otherwise let the database stamp the row with now().
    created_date = core_timezone.to_utc_aware(activity.created_at) if activity.created_at is not None else func.now()

    # Sanitize markdown fields to prevent XSS
    sanitized_description = core_sanitization.sanitize_markdown(activity.description)
    sanitized_private_notes = core_sanitization.sanitize_markdown(activity.private_notes)

    # Create a new activity object
    new_activity = activities_models.Activity(
        user_id=activity.user_id,
        description=sanitized_description,
        private_notes=sanitized_private_notes,
        distance=activity.distance,
        name=activity.name,
        activity_type=activity.activity_type,
        start_time=core_timezone.to_utc_aware(activity.start_time),
        end_time=core_timezone.to_utc_aware(activity.end_time),
        timezone=activity.timezone,
        total_elapsed_time=activity.total_elapsed_time,
        total_timer_time=(
            activity.total_timer_time if activity.total_timer_time is not None else activity.total_elapsed_time
        ),
        city=activity.city,
        town=activity.town,
        country=activity.country,
        created_at=created_date,
        elevation_gain=activity.elevation_gain,
        elevation_loss=activity.elevation_loss,
        pace=activity.pace,
        average_speed=activity.average_speed,
        max_speed=activity.max_speed,
        average_power=activity.average_power,
        max_power=activity.max_power,
        normalized_power=activity.normalized_power,
        average_hr=activity.average_hr,
        max_hr=activity.max_hr,
        average_cad=activity.average_cad,
        max_cad=activity.max_cad,
        workout_feeling=activity.workout_feeling,
        workout_rpe=activity.workout_rpe,
        calories=activity.calories,
        visibility=activity.visibility,
        gear_id=activity.gear_id,
        strava_gear_id=activity.strava_gear_id,
        strava_activity_id=activity.strava_activity_id,
        garminconnect_activity_id=activity.garminconnect_activity_id,
        garminconnect_gear_id=activity.garminconnect_gear_id,
        import_info=activity.import_info,
        is_hidden=activity.is_hidden if activity.is_hidden is not None else False,
        hide_start_time=activity.hide_start_time,
        hide_location=activity.hide_location,
        hide_map=activity.hide_map,
        hide_hr=activity.hide_hr,
        hide_power=activity.hide_power,
        hide_cadence=activity.hide_cadence,
        hide_elevation=activity.hide_elevation,
        hide_speed=activity.hide_speed,
        hide_pace=activity.hide_pace,
        hide_laps=activity.hide_laps,
        hide_workout_sets_steps=activity.hide_workout_sets_steps,
        hide_gear=activity.hide_gear,
        tracker_manufacturer=activity.tracker_manufacturer,
        tracker_model=activity.tracker_model,
        total_cycles=activity.total_cycles,
    )

    return new_activity


def _serialize_and_mask(
    activities: list[activities_models.Activity],
    *,
    requester_user_id: int | None = None,
    force_non_owner: bool = False,
    mask_private_notes: bool = True,
) -> list[activities_schema.Activity]:
    """Serialize ORM rows and apply visibility masking.

    Args:
        activities: ORM Activity rows.
        requester_user_id: ID of requesting user; treated as
            owner when matches the row's user_id. Ignored when
            ``force_non_owner`` is True.
        force_non_owner: When True, every row is masked as if
            the requester is not the owner.
        mask_private_notes: Whether to mask ``private_notes``
            for non-owners.

    Returns:
        List of Activity schema instances with visibility
        masking applied.
    """
    result: list[activities_schema.Activity] = []
    for orm_activity in activities:
        schema = activities_serializers.serialize_activity(orm_activity)
        is_owner = not force_non_owner and requester_user_id is not None and orm_activity.user_id == requester_user_id
        activities_serializers.apply_visibility_mask(
            schema,
            is_owner=is_owner,
            mask_private_notes=mask_private_notes,
        )
        result.append(schema)
    return result


def _apply_name_search(
    stmt,
    name_search: str,
):
    """Add a case-insensitive LIKE search across name/location.

    Escapes ``%``/``_`` so user input cannot inject wildcards.

    Args:
        stmt: SQLAlchemy ``select()`` statement.
        name_search: URL-encoded search term.

    Returns:
        Updated select statement.
    """
    raw = unquote(name_search).replace("+", " ").lower()
    pattern = f"%{escape_like(raw)}%"
    return stmt.where(
        or_(
            func.lower(activities_models.Activity.name).like(pattern, escape="\\"),
            func.lower(activities_models.Activity.town).like(pattern, escape="\\"),
            func.lower(activities_models.Activity.city).like(pattern, escape="\\"),
            func.lower(activities_models.Activity.country).like(pattern, escape="\\"),
        )
    )


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
        HTTPException: 500 on database error.
    """
    try:
        activities = db.execute(select(activities_models.Activity)).scalars().all()
        if not activities:
            return None
        return [activities_serializers.serialize_activity(a) for a in activities]
    except SQLAlchemyError as err:
        raise _internal_server_error(err, "get_all_activities") from err


def get_all_activities_for_migration(
    db: Session,
) -> list[activities_schema.ActivityMigrationRef]:
    """Return a lightweight reference for every activity (migration use only).

    Projects only the identity, owner, provider ids, and time bounds the
    data-backfill migrations read, so no ORM row leaves the CRUD layer.

    Args:
        db: Database session.

    Returns:
        A migration reference per activity, or an empty list when there are none.

    Raises:
        HTTPException: 500 on database error.
    """
    try:
        activities = db.execute(select(activities_models.Activity)).scalars().all()
        return [
            activities_schema.ActivityMigrationRef(
                id=activity.id,
                user_id=activity.user_id,
                start_time=activity.start_time,
                end_time=activity.end_time,
                strava_activity_id=activity.strava_activity_id,
                garminconnect_activity_id=activity.garminconnect_activity_id,
            )
            for activity in activities
        ]
    except SQLAlchemyError as err:
        raise _internal_server_error(err, "get_all_activities_for_migration") from err


def get_user_activities(
    user_id: int,
    db: Session,
    activity_type: int | None = None,
    start_date: date | None = None,
    end_date: date | None = None,
    name_search: str | None = None,
    user_is_owner: bool = True,
    requester_user_id: int | None = None,
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
        requester_user_id: Requesting user ID used to authorize
            followers-only rows when ``user_is_owner`` is False.

    Returns:
        List of activity schemas or None when no matches.

    Raises:
        HTTPException: 500 on database error.
    """
    try:
        stmt = select(activities_models.Activity).where(activities_models.Activity.user_id == user_id)
        stmt = _apply_activity_visibility_filter(
            stmt,
            user_is_owner=user_is_owner,
            requester_user_id=requester_user_id,
            db=db,
        )
        if activity_type:
            stmt = stmt.where(activities_models.Activity.activity_type == activity_type)
        if start_date:
            stmt = stmt.where(func.date(activities_models.Activity.start_time) >= start_date)
        if end_date:
            stmt = stmt.where(func.date(activities_models.Activity.start_time) <= end_date)
        if name_search:
            stmt = _apply_name_search(stmt, name_search)
        stmt = stmt.order_by(desc(activities_models.Activity.start_time))

        activities = db.execute(stmt).scalars().all()
        if not activities:
            return None
        return _serialize_and_mask(
            list(activities),
            requester_user_id=user_id if user_is_owner else None,
            force_non_owner=not user_is_owner,
        )
    except SQLAlchemyError as err:
        raise _internal_server_error(err, "get_user_activities") from err


def count_user_activities(
    user_id: int,
    db: Session,
    activity_type: int | None = None,
    start_date: date | None = None,
    end_date: date | None = None,
    name_search: str | None = None,
    user_is_owner: bool = True,
    requester_user_id: int | None = None,
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
        requester_user_id: Requesting user ID used to authorize
            followers-only rows when ``user_is_owner`` is False.

    Returns:
        Number of matching activities.

    Raises:
        HTTPException: 500 on database error.
    """
    try:
        stmt = (
            select(func.count())
            .select_from(activities_models.Activity)
            .where(activities_models.Activity.user_id == user_id)
        )
        stmt = _apply_activity_visibility_filter(
            stmt,
            user_is_owner=user_is_owner,
            requester_user_id=requester_user_id,
            db=db,
        )
        if activity_type:
            stmt = stmt.where(activities_models.Activity.activity_type == activity_type)
        if start_date:
            stmt = stmt.where(func.date(activities_models.Activity.start_time) >= start_date)
        if end_date:
            stmt = stmt.where(func.date(activities_models.Activity.start_time) <= end_date)
        if name_search:
            stmt = _apply_name_search(stmt, name_search)
        count = db.execute(stmt).scalar()
        return count or 0
    except SQLAlchemyError as err:
        raise _internal_server_error(err, "count_user_activities") from err


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
        HTTPException: 500 on database error.
    """
    try:
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
        return _serialize_and_mask(
            list(activities),
            requester_user_id=user_id,
        )
    except SQLAlchemyError as err:
        raise _internal_server_error(
            err,
            "get_user_activities_by_user_id_and_garminconnect_gear_set",
        ) from err


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
    requester_user_id: int | None = None,
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
        requester_user_id: Requesting user ID used to authorize
            followers-only rows when ``user_is_owner`` is False.

    Returns:
        List of activity schemas or None when empty.

    Raises:
        HTTPException: 500 on database error.
    """
    try:
        stmt = select(activities_models.Activity).where(
            activities_models.Activity.user_id == user_id,
        )
        stmt = _apply_activity_visibility_filter(
            stmt,
            user_is_owner=user_is_owner,
            requester_user_id=requester_user_id,
            db=db,
        )
        if activity_type:
            stmt = stmt.where(activities_models.Activity.activity_type == activity_type)
        if start_date:
            stmt = stmt.where(func.date(activities_models.Activity.start_time) >= start_date)
        if end_date:
            stmt = stmt.where(func.date(activities_models.Activity.start_time) <= end_date)
        if name_search:
            stmt = _apply_name_search(stmt, name_search)

        sort_ascending = bool(sort_order and sort_order.lower() == "asc")

        if sort_by == "location":
            location_cols = [
                func.coalesce(activities_models.Activity.country, ""),
                func.coalesce(activities_models.Activity.city, ""),
                func.coalesce(activities_models.Activity.town, ""),
            ]
            order_cols = [col.asc() if sort_ascending else col.desc() for col in location_cols]
            stmt = stmt.order_by(*order_cols)
        else:
            sort_column = SORT_MAP.get(sort_by or "", activities_models.Activity.start_time)
            if sort_column in _NUMERIC_SORT_COLUMNS:
                ordered = func.coalesce(sort_column, -999999)
                stmt = stmt.order_by(ordered.asc() if sort_ascending else ordered.desc())
            else:
                stmt = stmt.order_by(sort_column.asc() if sort_ascending else sort_column.desc())

        stmt = stmt.offset((page_number - 1) * num_records).limit(num_records)

        activities = db.execute(stmt).scalars().all()
        if not activities:
            return None
        return _serialize_and_mask(
            list(activities),
            requester_user_id=user_id if user_is_owner else None,
            force_non_owner=not user_is_owner,
        )
    except SQLAlchemyError as err:
        raise _internal_server_error(err, "get_user_activities_with_pagination") from err


def get_distinct_activity_types_for_user(user_id: int, db: Session) -> dict[int, str]:
    """Map distinct activity types owned by a user to names.

    Args:
        user_id: Owner user ID.
        db: Database session.

    Returns:
        Dict of activity_type -> human readable name.

    Raises:
        HTTPException: 500 on database error.
    """
    try:
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
    except SQLAlchemyError as err:
        raise _internal_server_error(err, "get_distinct_activity_types_for_user") from err


def get_user_activities_per_timeframe(
    user_id: int,
    start: datetime,
    end: datetime,
    db: Session,
    user_is_owner: bool = False,
    requester_user_id: int | None = None,
) -> list[activities_schema.Activity] | None:
    """Get a user's activities within a date range.

    Args:
        user_id: Owner user ID.
        start: Inclusive start datetime.
        end: Inclusive end datetime.
        db: Database session.
        user_is_owner: When False, private/hidden activities
            are excluded.
        requester_user_id: Requesting user ID used to authorize
            followers-only rows when ``user_is_owner`` is False.

    Returns:
        List of activity schemas or None when empty.

    Raises:
        HTTPException: 500 on database error.
    """
    try:
        stmt = (
            select(activities_models.Activity)
            .where(
                activities_models.Activity.user_id == user_id,
                func.date(activities_models.Activity.start_time) >= start.date(),
                func.date(activities_models.Activity.start_time) <= end.date(),
            )
            .order_by(desc(activities_models.Activity.start_time))
        )
        stmt = _apply_activity_visibility_filter(
            stmt,
            user_is_owner=user_is_owner,
            requester_user_id=requester_user_id,
            db=db,
        )
        activities = db.execute(stmt).scalars().all()
        if not activities:
            return None
        return _serialize_and_mask(
            list(activities),
            requester_user_id=user_id if user_is_owner else None,
            force_non_owner=not user_is_owner,
        )
    except SQLAlchemyError as err:
        raise _internal_server_error(err, "get_user_activities_per_timeframe") from err


def get_user_activities_per_timeframe_and_activity_type(
    user_id: int,
    activity_type: int,
    start: datetime,
    end: datetime,
    db: Session,
    user_is_owner: bool = False,
    requester_user_id: int | None = None,
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
        requester_user_id: Requesting user ID used to authorize
            followers-only rows when ``user_is_owner`` is False.

    Returns:
        List of activity schemas or None when empty.

    Raises:
        HTTPException: 500 on database error.
    """
    try:
        stmt = (
            select(activities_models.Activity)
            .where(
                activities_models.Activity.user_id == user_id,
                activities_models.Activity.activity_type == activity_type,
                func.date(activities_models.Activity.start_time) >= start.date(),
                func.date(activities_models.Activity.start_time) <= end.date(),
            )
            .order_by(desc(activities_models.Activity.start_time))
        )
        stmt = _apply_activity_visibility_filter(
            stmt,
            user_is_owner=user_is_owner,
            requester_user_id=requester_user_id,
            db=db,
        )
        activities = db.execute(stmt).scalars().all()
        if not activities:
            return None
        return _serialize_and_mask(
            list(activities),
            requester_user_id=user_id if user_is_owner else None,
            force_non_owner=not user_is_owner,
        )
    except SQLAlchemyError as err:
        raise _internal_server_error(
            err,
            "get_user_activities_per_timeframe_and_activity_type",
        ) from err


def get_user_activities_per_timeframe_and_activity_types(
    user_id: int,
    activity_types: list[int],
    start: datetime,
    end: datetime,
    db: Session,
    user_is_owner: bool = False,
    requester_user_id: int | None = None,
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
        requester_user_id: Requesting user ID used to authorize
            followers-only rows when ``user_is_owner`` is False.
        exclude_hidden: When True, hidden activities are excluded
            even for owner requests.

    Returns:
        List of activity schemas.

    Raises:
        HTTPException: 500 on database error.
    """
    try:
        stmt = (
            select(activities_models.Activity)
            .where(
                activities_models.Activity.user_id == user_id,
                activities_models.Activity.activity_type.in_(activity_types),
                func.date(activities_models.Activity.start_time) >= start.date(),
                func.date(activities_models.Activity.start_time) <= end.date(),
            )
            .order_by(desc(activities_models.Activity.start_time))
        )
        if exclude_hidden:
            stmt = stmt.where(activities_models.Activity.is_hidden.is_(False))
        stmt = _apply_activity_visibility_filter(
            stmt,
            user_is_owner=user_is_owner,
            requester_user_id=requester_user_id,
            db=db,
        )
        activities = db.execute(stmt).scalars().all()
        if not activities:
            return []
        return _serialize_and_mask(
            list(activities),
            requester_user_id=user_id if user_is_owner else None,
            force_non_owner=not user_is_owner,
        )
    except SQLAlchemyError as err:
        raise _internal_server_error(
            err,
            "get_user_activities_per_timeframe_and_activity_types",
        ) from err


def get_user_following_activities_per_timeframe(
    user_id: int,
    start: datetime,
    end: datetime,
    db: Session,
) -> list[activities_schema.Activity] | None:
    """Get followed users' activities within a date range.

    Args:
        user_id: Requesting user ID (the follower).
        start: Inclusive start datetime.
        end: Inclusive end datetime.
        db: Database session.

    Returns:
        List of activity schemas or None when empty.

    Raises:
        HTTPException: 500 on database error.
    """
    try:
        followee_ids = followers_service.list_accepted_followee_ids(user_id, db)
        if not followee_ids:
            return None
        stmt = (
            select(activities_models.Activity)
            .where(
                activities_models.Activity.user_id.in_(followee_ids),
                activities_models.Activity.visibility.in_([0, 1]),
                activities_models.Activity.is_hidden.is_(False),
                activities_models.Activity.strava_activity_id.is_(None),
                func.date(activities_models.Activity.start_time) >= start.date(),
                func.date(activities_models.Activity.start_time) <= end.date(),
            )
            .order_by(desc(activities_models.Activity.start_time))
        )
        activities = db.execute(stmt).scalars().all()
        if not activities:
            return None
        return _serialize_and_mask(list(activities), force_non_owner=True)
    except SQLAlchemyError as err:
        raise _internal_server_error(err, "get_user_following_activities_per_timeframe") from err


def get_user_following_activities_with_pagination(
    followee_ids: list[int], page_number: int, num_records: int, db: Session
) -> list[activities_schema.Activity] | None:
    """Get a page of activities from a set of followed users.

    Args:
        followee_ids: The requester's accepted-followee user ids, resolved by the
            caller through the followers service interface (kept out of the ORM
            layer so the feed's cross-domain dependency lives in the service).
        page_number: 1-based page number.
        num_records: Records per page.
        db: Database session.

    Returns:
        List of activity schemas or None when empty.

    Raises:
        HTTPException: 500 on database error.
    """
    try:
        if not followee_ids:
            return None
        stmt = (
            select(activities_models.Activity)
            .where(
                activities_models.Activity.user_id.in_(followee_ids),
                activities_models.Activity.visibility.in_([0, 1]),
                activities_models.Activity.is_hidden.is_(False),
                activities_models.Activity.strava_activity_id.is_(None),
            )
            .order_by(desc(activities_models.Activity.start_time))
            .offset((page_number - 1) * num_records)
            .limit(num_records)
        )
        activities = db.execute(stmt).scalars().all()
        if not activities:
            return None
        return _serialize_and_mask(list(activities), force_non_owner=True)
    except SQLAlchemyError as err:
        raise _internal_server_error(err, "get_user_following_activities_with_pagination") from err


def get_user_following_activities(user_id: int, db: Session) -> list[activities_schema.Activity] | None:
    """Get all activities from users a user follows.

    Args:
        user_id: Requesting user ID.
        db: Database session.

    Returns:
        List of activity schemas or None when empty.

    Raises:
        HTTPException: 500 on database error.
    """
    try:
        followee_ids = followers_service.list_accepted_followee_ids(user_id, db)
        if not followee_ids:
            return None
        stmt = select(activities_models.Activity).where(
            activities_models.Activity.user_id.in_(followee_ids),
            activities_models.Activity.visibility.in_([0, 1]),
            activities_models.Activity.is_hidden.is_(False),
            activities_models.Activity.strava_activity_id.is_(None),
        )
        activities = db.execute(stmt).scalars().all()
        if not activities:
            return None
        return [activities_serializers.serialize_activity(a) for a in activities]
    except SQLAlchemyError as err:
        raise _internal_server_error(err, "get_user_following_activities") from err


def count_user_following_activities(followee_ids: list[int], db: Session) -> int:
    """Count activities from a set of followed users.

    Uses a SQL ``COUNT(*)`` so counting never loads or serializes rows.

    Args:
        followee_ids: The requester's accepted-followee user ids, resolved by the
            caller through the followers service interface.
        db: Database session.

    Returns:
        Number of following-feed activities.

    Raises:
        HTTPException: 500 on database error.
    """
    try:
        if not followee_ids:
            return 0
        stmt = (
            select(func.count())
            .select_from(activities_models.Activity)
            .where(
                activities_models.Activity.user_id.in_(followee_ids),
                activities_models.Activity.visibility.in_([0, 1]),
                activities_models.Activity.is_hidden.is_(False),
                activities_models.Activity.strava_activity_id.is_(None),
            )
        )
        count = db.execute(stmt).scalar()
        return count or 0
    except SQLAlchemyError as err:
        raise _internal_server_error(err, "count_user_following_activities") from err


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
        HTTPException: 500 on database error.
    """
    try:
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
    except SQLAlchemyError as err:
        raise _internal_server_error(err, "get_gear_activities_count_by_user_id") from err


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
        HTTPException: 500 on database error.
    """
    try:
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
        return _serialize_and_mask(
            list(activities),
            requester_user_id=user_id,
        )
    except SQLAlchemyError as err:
        raise _internal_server_error(err, "get_user_activities_by_gear_id_and_user_id") from err


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
        HTTPException: 500 on database error.
    """
    try:
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
        return _serialize_and_mask(
            list(activities),
            requester_user_id=user_id,
        )
    except SQLAlchemyError as err:
        raise _internal_server_error(
            err,
            "get_user_activities_by_gear_id_and_user_id_with_pagination",
        ) from err


def get_activity_by_id_from_user_id_or_has_visibility(
    activity_id: int, user_id: int, db: Session
) -> activities_schema.Activity | None:
    """Get an activity by ID if owned or visible to the user.

    Args:
        activity_id: Activity ID.
        user_id: Requesting user ID.
        db: Database session.

    Returns:
        Activity schema or None if not found / not visible.

    Raises:
        HTTPException: 500 on database error.
    """
    try:
        stmt = select(activities_models.Activity).where(
            or_(
                activities_models.Activity.user_id == user_id,
                _visible_to_requester_condition(user_id, db),
            ),
            activities_models.Activity.id == activity_id,
        )
        activity = db.execute(stmt).scalar_one_or_none()
        if not activity:
            return None
        schema = activities_serializers.serialize_activity(activity)
        is_owner = activity.user_id == user_id
        activities_serializers.apply_visibility_mask(schema, is_owner=is_owner)
        core_logger.print_to_log(
            f"Served activity {activity_id} to user {user_id} (owner={is_owner})",
            "debug",
        )
        return schema
    except SQLAlchemyError as err:
        raise _internal_server_error(err, "get_activity_by_id_from_user_id_or_has_visibility") from err


def get_viewable_activity_by_id_for_user(
    activity_id: int, user_id: int, db: Session
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

    Returns:
        The activity schema when the user may view it, otherwise ``None``.

    Raises:
        HTTPException: 500 on database error.
    """
    try:
        stmt = select(activities_models.Activity).where(
            or_(
                activities_models.Activity.user_id == user_id,
                _visible_to_requester_condition(user_id, db),
            ),
            activities_models.Activity.id == activity_id,
        )
        activity = db.execute(stmt).scalar_one_or_none()
        if not activity:
            return None
        return activities_serializers.serialize_activity(activity)
    except SQLAlchemyError as err:
        raise _internal_server_error(err, "get_viewable_activity_by_id_for_user") from err


def get_activity_by_id_if_is_public(activity_id: int, db: Session) -> activities_schema.Activity | None:
    """Get an activity by ID if it is publicly shareable.

    Args:
        activity_id: Activity ID.
        db: Database session.

    Returns:
        Activity schema or None when not public / not found.

    Raises:
        HTTPException: 500 on database error.
    """
    try:
        server_settings = server_settings_utils.get_server_settings_or_404(db)
        if not server_settings.public_shareable_links:
            return None

        stmt = select(activities_models.Activity).where(
            activities_models.Activity.visibility == 0,
            activities_models.Activity.is_hidden.is_(False),
            activities_models.Activity.id == activity_id,
        )
        activity = db.execute(stmt).scalar_one_or_none()
        if not activity:
            return None
        schema = activities_serializers.serialize_activity(activity)
        activities_serializers.apply_visibility_mask(schema, is_owner=False)
        core_logger.print_to_log(f"Served public activity {activity_id}", "debug")
        return schema
    except SQLAlchemyError as err:
        raise _internal_server_error(err, "get_activity_by_id_if_is_public") from err


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
       :func:`get_activity_by_id_if_is_public`, which enforces the server-wide
       ``public_shareable_links`` setting, ``visibility == 0`` **and**
       ``is_hidden is False``.
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
        HTTPException: 500 on database error.
    """
    activity = get_activity_by_id_if_is_public(activity_id, db)
    if activity is None:
        core_logger.print_to_log(
            f"Public child read denied for activity {activity_id} ({hide_attr}): not publicly shareable",
            "debug",
        )
        return None

    if getattr(activity, hide_attr):
        core_logger.print_to_log(
            f"Public child read denied for activity {activity_id}: {hide_attr} is set",
            "debug",
        )
        return None

    return activity


def get_activity_by_id(activity_id: int, db: Session) -> activities_schema.Activity | None:
    """Get an activity by ID without permission checks.

    Args:
        activity_id: Activity ID.
        db: Database session.

    Returns:
        Activity schema or None when not found.

    Raises:
        HTTPException: 500 on database error.
    """
    try:
        stmt = select(activities_models.Activity).where(
            activities_models.Activity.id == activity_id,
        )
        activity = db.execute(stmt).scalar_one_or_none()
        if not activity:
            return None
        return activities_serializers.serialize_activity(activity)
    except SQLAlchemyError as err:
        raise _internal_server_error(err, "get_activity_by_id") from err


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
        HTTPException: 500 on database error.
    """
    try:
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
    except SQLAlchemyError as err:
        raise _internal_server_error(err, "get_activity_by_start_time") from err


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
        HTTPException: 500 on database error.
    """
    try:
        stmt = select(activities_models.Activity).where(
            activities_models.Activity.user_id == user_id,
            activities_models.Activity.dedup_key == dedup_key,
        )
        activity = db.execute(stmt).scalars().first()
        if not activity:
            return None
        return activities_serializers.serialize_activity(activity)
    except SQLAlchemyError as err:
        raise _internal_server_error(err, "get_activity_by_dedup_key") from err


def get_activity_by_id_from_user_id(activity_id: int, user_id: int, db: Session) -> activities_schema.Activity | None:
    """Get a user's activity by ID.

    Args:
        activity_id: Activity ID.
        user_id: Owner user ID.
        db: Database session.

    Returns:
        Activity schema or None when not found.

    Raises:
        HTTPException: 500 on database error.
    """
    try:
        stmt = select(activities_models.Activity).where(
            activities_models.Activity.user_id == user_id,
            activities_models.Activity.id == activity_id,
        )
        activity = db.execute(stmt).scalar_one_or_none()
        if not activity:
            return None
        return activities_serializers.serialize_activity(activity)
    except SQLAlchemyError as err:
        raise _internal_server_error(err, "get_activity_by_id_from_user_id") from err


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
        HTTPException: 500 on database error.
    """
    try:
        stmt = select(activities_models.Activity).where(
            activities_models.Activity.user_id == user_id,
            activities_models.Activity.strava_activity_id == activity_strava_id,
        )
        activity = db.execute(stmt).scalar_one_or_none()
        if not activity:
            return None
        return activities_serializers.serialize_activity(activity)
    except SQLAlchemyError as err:
        raise _internal_server_error(err, "get_activity_by_strava_id_from_user_id") from err


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
        HTTPException: 500 on database error.
    """
    try:
        stmt = select(activities_models.Activity).where(
            activities_models.Activity.user_id == user_id,
            activities_models.Activity.garminconnect_activity_id == activity_garminconnect_id,
        )
        activity = db.execute(stmt).scalars().first()
        if not activity:
            return None
        return activities_serializers.serialize_activity(activity)
    except SQLAlchemyError as err:
        raise _internal_server_error(err, "get_activity_by_garminconnect_id_from_user_id") from err


def get_activities_if_contains_name(name: str, user_id: int, db: Session) -> list[activities_schema.Activity] | None:
    """Search a user's activities by partial name match.

    Args:
        name: URL-encoded partial name.
        user_id: Owner user ID.
        db: Database session.

    Returns:
        List of activity schemas or None when no matches.

    Raises:
        HTTPException: 500 on database error.
    """
    try:
        partial_name = unquote(name).replace("+", " ").lower()
        pattern = f"%{escape_like(partial_name)}%"
        stmt = (
            select(activities_models.Activity)
            .where(
                activities_models.Activity.user_id == user_id,
                func.lower(activities_models.Activity.name).like(pattern, escape="\\"),
            )
            .order_by(desc(activities_models.Activity.start_time))
        )
        activities = db.execute(stmt).scalars().all()
        if not activities:
            return None
        return _serialize_and_mask(
            list(activities),
            requester_user_id=user_id,
        )
    except SQLAlchemyError as err:
        raise _internal_server_error(err, "get_activities_if_contains_name") from err


def create_activity(
    activity: activities_schema.ActivityCore,
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
        The provided activity schema with generated ID and ``created_at``
        populated. ``is_hidden`` is set ``True`` when the start time duplicates
        an existing activity — the signal the caller forwards to the
        ``activity.created`` notification subscriber.

    Raises:
        HTTPException: 500 on database error.
    """
    try:
        if activity.user_id is None:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="Activity user_id is required",
            )

        # Normalize the start time to a UTC-aware datetime at the persistence
        # boundary. Parsers emit naive UTC wall-clock values and providers emit
        # ISO strings; to_utc_aware coerces both to aware UTC and returns None for
        # a missing value, so we never persist or compare a naive/absent start
        # time (this is also what keeps get_activity_by_start_time from being
        # handed a None).
        normalized_start_time = core_timezone.to_utc_aware(activity.start_time)
        if normalized_start_time is None:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="Activity start_time is required and must be a valid datetime",
            )

        activity_start_time_exists = get_activity_by_start_time(normalized_start_time, activity.user_id, db)
        if activity_start_time_exists:
            activity.is_hidden = True

        new_activity = _transform_schema_activity_to_model_activity(activity)
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

        activity.id = new_activity.id
        activity.created_at = new_activity.created_at

        core_logger.print_to_log(
            f"Created activity {new_activity.id} for user {activity.user_id}"
            + (" (marked hidden: duplicate start time)" if activity_start_time_exists else ""),
            "debug",
        )

        return activity
    except SQLAlchemyError as err:
        db.rollback()
        raise _internal_server_error(err, "create_activity") from err


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
        HTTPException: 500 on database error.
    """
    try:
        stmt = select(activities_models.Activity).where(activities_models.Activity.id == activity_id)
        db_activity = db.execute(stmt).scalar_one_or_none()
        if db_activity is None:
            core_logger.print_to_log(
                f"Activity {activity_id} not found when setting thumbnail path",
                "warning",
            )
            return
        db_activity.map_thumbnail_path = thumbnail_path
        db.commit()
    except SQLAlchemyError as err:
        db.rollback()
        raise _internal_server_error(err, "set_activity_thumbnail_path") from err


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
        HTTPException: 500 on database error.
    """
    try:
        stmt = select(activities_models.Activity).where(activities_models.Activity.id == activity_id)
        db_activity = db.execute(stmt).scalar_one_or_none()
        if db_activity is None:
            core_logger.print_to_log(
                f"Activity {activity_id} not found when updating location",
                "warning",
            )
            return False
        db_activity.city = city
        db_activity.town = town
        db_activity.country = country
        db.commit()
        return True
    except SQLAlchemyError as err:
        db.rollback()
        raise _internal_server_error(err, "update_activity_location") from err


def get_activities_missing_location(
    db: Session,
    limit: int = 200,
) -> list[activities_schema.ActivityLocationRef]:
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
        return [activities_schema.ActivityLocationRef(id=activity_id) for activity_id in ids]
    except SQLAlchemyError as err:
        core_logger.print_to_log(
            f"Error in get_activities_missing_location: {err}",
            "error",
            exc=err,
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
        core_logger.print_to_log(
            f"Error in clear_all_activity_thumbnail_paths: {err}",
            "error",
            exc=err,
        )


def get_activities_with_thumbnail(
    db: Session,
) -> list[activities_schema.ActivityThumbnailRef]:
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
            activities_schema.ActivityThumbnailRef(id=row.id, map_thumbnail_path=row.map_thumbnail_path) for row in rows
        ]
    except SQLAlchemyError as err:
        core_logger.print_to_log(
            f"Error in get_activities_with_thumbnail: {err}",
            "error",
            exc=err,
        )
        return []


def get_activities_without_thumbnail(
    db: Session,
) -> list[activities_schema.ActivityThumbnailRef]:
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
            activities_schema.ActivityThumbnailRef(id=row.id, map_thumbnail_path=row.map_thumbnail_path) for row in rows
        ]
    except SQLAlchemyError as err:
        core_logger.print_to_log(
            f"Error in get_activities_without_thumbnail: {err}",
            "error",
            exc=err,
        )
        return []


def get_activities_with_legacy_thumbnail_path(
    db: Session,
    after_id: int = 0,
    limit: int = 200,
) -> list[activities_schema.ActivityThumbnailRef]:
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
            activities_schema.ActivityThumbnailRef(id=row.id, map_thumbnail_path=row.map_thumbnail_path) for row in rows
        ]
    except SQLAlchemyError as err:
        core_logger.print_to_log(
            f"Error in get_activities_with_legacy_thumbnail_path: {err}",
            "error",
            exc=err,
        )
        return []


def edit_activity(
    user_id: int,
    activity_id: int,
    activity_attributes: activities_schema.ActivityEdit | activities_schema.Activity,
    db: Session,
) -> activities_schema.Activity:
    """Apply partial updates to a user's activity.

    Args:
        user_id: Owner user ID.
        activity_id: ID of the activity to update (from the request path).
        activity_attributes: Pydantic model carrying the fields to update;
            only the fields explicitly set are applied.
        db: Database session.

    Returns:
        The updated activity as a serialized schema.

    Raises:
        HTTPException: 404 when the activity is missing or
            500 on database error.
    """
    try:
        stmt = select(activities_models.Activity).where(
            activities_models.Activity.user_id == user_id,
            activities_models.Activity.id == activity_id,
        )
        db_activity = db.execute(stmt).scalar_one_or_none()
        if db_activity is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Activity not found",
            )

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

        db.commit()
        db.refresh(db_activity)
        core_logger.print_to_log(
            f"Edited activity {db_activity.id} for user {user_id} (fields: {sorted(activity_data.keys())})",
            "debug",
        )
        return activities_serializers.serialize_activity(db_activity)
    except HTTPException:
        raise
    except SQLAlchemyError as err:
        db.rollback()
        raise _internal_server_error(err, "edit_activity") from err


def edit_user_activities_visibility(user_id: int, visibility: int, db: Session) -> int:
    """Bulk-update the visibility for every activity of a user.

    Args:
        user_id: Owner user ID.
        visibility: New visibility value (0, 1, 2).
        db: Database session.

    Returns:
        Number of activities updated.

    Raises:
        HTTPException: 500 on database error.
    """
    try:
        stmt = (
            sa_update(activities_models.Activity)
            .where(activities_models.Activity.user_id == user_id)
            .values(visibility=visibility)
        )
        # Session.execute() is typed to return the base Result; an UPDATE/DELETE
        # always yields a CursorResult at runtime, which is what exposes rowcount.
        result = cast("CursorResult[Any]", db.execute(stmt))
        db.commit()
        return result.rowcount or 0
    except SQLAlchemyError as err:
        db.rollback()
        raise _internal_server_error(err, "edit_user_activities_visibility") from err


def bulk_set_activities_gear_id(
    user_id: int,
    gear_assignments: dict[int, int | None],
    db: Session,
) -> int:
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

    Returns:
        Total number of rows updated across all groups.

    Raises:
        HTTPException: 500 on database error.
    """
    if not gear_assignments:
        return 0
    try:
        by_gear: dict[int | None, list[int]] = defaultdict(list)
        for activity_id, gear_id in gear_assignments.items():
            by_gear[gear_id].append(activity_id)

        total = 0
        for gear_id, activity_ids in by_gear.items():
            stmt = (
                sa_update(activities_models.Activity)
                .where(
                    activities_models.Activity.user_id == user_id,
                    activities_models.Activity.id.in_(activity_ids),
                )
                .values(gear_id=gear_id)
            )
            result = cast("CursorResult[Any]", db.execute(stmt))
            total += result.rowcount or 0
        db.commit()
        return total
    except SQLAlchemyError as err:
        db.rollback()
        raise _internal_server_error(err, "bulk_set_activities_gear_id") from err


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
        HTTPException: 500 on database error.
    """
    try:
        stmt = (
            sa_update(activities_models.Activity)
            .where(
                activities_models.Activity.id == activity_id,
                activities_models.Activity.user_id == user_id,
            )
            .values(gear_id=gear_id)
        )
        db.execute(stmt)
        db.commit()
    except SQLAlchemyError as err:
        db.rollback()
        raise _internal_server_error(err, "update_activity_gear_id") from err


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
        HTTPException: 404 when the activity is missing or not owned by
            ``user_id``, or 500 on database error.
    """
    try:
        stmt = sa_delete(activities_models.Activity).where(
            activities_models.Activity.id == activity_id,
            activities_models.Activity.user_id == user_id,
        )
        result = cast("CursorResult[Any]", db.execute(stmt))
        if result.rowcount == 0:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Activity with id {activity_id} not found",
            )
        if commit:
            db.commit()
        core_logger.print_to_log(f"Deleted activity {activity_id} for user {user_id}", "debug")
    except HTTPException:
        db.rollback()
        raise
    except SQLAlchemyError as err:
        db.rollback()
        raise _internal_server_error(err, "delete_activity") from err


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
        HTTPException: 500 on database error.
    """
    try:
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
        core_logger.print_to_log(
            f"Deleted {len(deleted_ids)} Strava activity/activities for user {user_id}",
            "info",
        )
        return deleted_ids
    except SQLAlchemyError as err:
        db.rollback()
        raise _internal_server_error(err, "delete_all_strava_activities_for_user") from err


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
        HTTPException: 500 on database error.
    """
    try:
        stmt = (
            sa_delete(activities_models.Activity)
            .where(activities_models.Activity.user_id == user_id)
            .returning(activities_models.Activity.id)
        )
        deleted_ids = [row_id for (row_id,) in db.execute(stmt).all()]
        if commit:
            db.commit()
        core_logger.print_to_log(
            f"Deleted {len(deleted_ids)} activity/activities for user {user_id}",
            "info",
        )
        return deleted_ids
    except SQLAlchemyError as err:
        db.rollback()
        raise _internal_server_error(err, "delete_all_activities_for_user") from err
