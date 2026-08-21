"""Application-layer orchestration for reading activities.

Thin sync routes delegate their read/stats/feed orchestration here: timeframe
math, owner-vs-requester scoping, aggregate stats, and the following-feed access
guard. Functions return schemas / DTOs / primitives and never expose ORM
instances. Access-control failures raise the transport-agnostic domain errors in
:mod:`core.exceptions`, which the API boundary renders — this layer states *what*
went wrong, never which HTTP status to send, so it stays usable from the durable
job worker and unit-testable without FastAPI.

Also the surface the module's **sibling sub-packages** read the activity row
through (see *Derived-artifact maintenance* at the end of the file). The derived
subsystems — thumbnails, geocoding, media — used to import ``activity.crud``
directly, which made every one of them a second owner of the activities table.
"""

import calendar
from datetime import UTC, date, datetime, time, timedelta

from sqlalchemy.orm import Session
from sqlalchemy.orm.exc import StaleDataError

import core.etag as core_etag
import core.exceptions as core_exceptions
import core.logger as core_logger
import core.pagination as core_pagination
import modules.activities.activity.contracts as activities_contracts
import modules.activities.activity.crud as activities_crud
import modules.activities.activity.event_publishers as activity_event_publishers
import modules.activities.activity.schema as activities_schema
import modules.activities.activity.stats as activities_stats
import modules.followers.integration_service as followers_integration
import modules.server_settings.integration_service as server_settings_integration
import modules.users.users.integration_service as users_integration_service

logger = core_logger.get_logger(__name__)


def _followees_of(requester_user_id: int | None, db: Session) -> list[int]:
    """Resolve whose followers-only activities the requester may see.

    The cross-domain half of the visibility rule, answered here so the queries
    below receive a plain list of ids. Persistence asking the followers module a
    question mid-``SELECT`` is a service decision in the wrong layer.

    Args:
        requester_user_id: The authenticated caller, or ``None`` when anonymous.
        db: Database session.

    Returns:
        The requester's accepted-followee user ids, empty when anonymous.
    """
    if requester_user_id is None:
        return []
    return followers_integration.list_accepted_followee_ids(requester_user_id, db)


def get_activities_in_timeframe(
    user_id: int,
    start: datetime,
    end: datetime,
    requester_user_id: int,
    db: Session,
) -> list[activities_schema.Activity] | None:
    """Return a user's activities in ``[start, end]`` scoped to the requester.

    The owner sees all of their activities; any other requester sees only the
    ones visible to them (the CRUD layer applies the visibility mask).

    Args:
        user_id: The owner of the activities.
        start: Inclusive start of the window (timezone-aware UTC).
        end: Inclusive end of the window (timezone-aware UTC).
        requester_user_id: The authenticated user making the request.
        db: Database session.

    Returns:
        The scoped activities, or ``None`` when there are none.
    """
    is_owner = user_id == requester_user_id
    logger.debug(
        "Listing activities in timeframe",
        extra=core_logger.context(
            user_id=user_id,
            requester_user_id=requester_user_id,
            is_owner=is_owner,
            window_start=str(start),
            window_end=str(end),
        ),
    )
    if is_owner:
        return activities_crud.get_user_activities_per_timeframe(user_id, start, end, db, True)
    return activities_crud.get_user_activities_per_timeframe(
        user_id,
        start,
        end,
        db,
        False,
        followee_ids=_followees_of(requester_user_id, db),
    )


def _anchor_date(anchor: date | None, requester_user_id: int, db: Session) -> datetime:
    """Return the midnight-aligned day the week/month window is built around.

    ``anchor`` is the *caller's* local calendar date, sent by the client because
    the request itself carries no timezone. When it is omitted we fall back to
    today in the requester's own configured zone, which is the same frame of
    reference the client would have sent. Falling back to the server's UTC date
    instead put "this week" and "this month" one period off around their
    boundaries: a day behind for up to 13 hours at UTC+13, a day ahead for up to
    11 at UTC-11.

    Args:
        anchor: The caller's local date, or ``None`` to resolve it server-side.
        requester_user_id: The authenticated user, whose timezone defines
            "today" when ``anchor`` is omitted.
        db: Database session.

    Returns:
        A midnight-aligned UTC datetime for the anchor day.
    """
    if anchor is None:
        anchor = users_integration_service.local_today(requester_user_id, db)
    return datetime.combine(anchor, time.min, tzinfo=UTC)


def _week_bounds(
    requester_user_id: int,
    db: Session,
    week_number: int = 0,
    anchor: date | None = None,
) -> tuple[datetime, datetime]:
    """Return the (start, end) of the week ``week_number`` weeks ago (0 = current).

    Both bounds are midnight-aligned so the window is a real calendar week
    (Monday 00:00 through Sunday, inclusive). They previously carried the current
    time of day, which made "this week" a rolling span anchored on *now* rather
    than on the week's boundaries.
    """
    today = _anchor_date(anchor, requester_user_id, db)
    start_of_week = today - timedelta(days=(today.weekday() + 7 * week_number))
    return start_of_week, start_of_week + timedelta(days=6)


def _month_bounds(
    requester_user_id: int,
    db: Session,
    anchor: date | None = None,
) -> tuple[datetime, datetime]:
    """Return the (start, end) of the calendar month containing the anchor day.

    Midnight-aligned for the same reason as :func:`_week_bounds`: keeping the
    current time of day meant activities recorded on the 1st before "now" fell
    outside the month window.
    """
    today = _anchor_date(anchor, requester_user_id, db)
    start_of_month = today.replace(day=1)
    end_of_month = start_of_month.replace(day=calendar.monthrange(today.year, today.month)[1])
    return start_of_month, end_of_month


def week_stats(
    user_id: int,
    requester_user_id: int,
    db: Session,
    anchor: date | None = None,
) -> activities_schema.ActivityStats:
    """Aggregate per-sport stats for a user's current-week activities."""
    start, end = _week_bounds(requester_user_id, db, 0, anchor)
    activities = get_activities_in_timeframe(user_id, start, end, requester_user_id, db)
    if activities:
        return activities_stats.calculate_activity_stats(activities)
    return activities_schema.ActivityStats()


def month_stats(
    user_id: int,
    requester_user_id: int,
    db: Session,
    anchor: date | None = None,
) -> activities_schema.ActivityStats:
    """Aggregate per-sport stats for a user's current-month activities."""
    start, end = _month_bounds(requester_user_id, db, anchor)
    activities = get_activities_in_timeframe(user_id, start, end, requester_user_id, db)
    if activities:
        return activities_stats.calculate_activity_stats(activities)
    return activities_schema.ActivityStats()


def period_stats(
    user_id: int,
    period: str,
    requester_user_id: int,
    db: Session,
    anchor: date | None = None,
) -> activities_schema.ActivityStats:
    """Aggregate per-sport stats for a user's ``week`` or ``month`` (default week).

    Args:
        user_id: The user whose stats to aggregate.
        period: ``week`` or ``month``.
        requester_user_id: The authenticated user making the request.
        db: Database session.
        anchor: The caller's local calendar date, used to decide which week or
            month is "current". Falls back to today in the requester's timezone.
    """
    logger.debug(
        "Aggregating period stats",
        extra=core_logger.context(user_id=user_id, period=period, requester_user_id=requester_user_id, anchor=anchor),
    )
    if period == "month":
        return month_stats(user_id, requester_user_id, db, anchor)
    return week_stats(user_id, requester_user_id, db, anchor)


def count_user_activities(
    user_id: int,
    db: Session,
    *,
    activity_type: int | None = None,
    start_date: date | None = None,
    end_date: date | None = None,
    name_search: str | None = None,
) -> int:
    """Count a user's own activities matching the given filters."""
    return activities_crud.count_user_activities(
        user_id=user_id,
        db=db,
        activity_type=activity_type,
        start_date=start_date,
        end_date=end_date,
        name_search=name_search,
    )


def list_gear_activities(
    user_id: int,
    gear_id: int,
    page_number: int | None,
    num_records: int | None,
    db: Session,
) -> list[activities_schema.Activity] | None:
    """List a user's activities for a gear (paginated when page/size are given)."""
    if page_number is not None and num_records is not None:
        return activities_crud.get_user_activities_by_gear_id_and_user_id_with_pagination(
            user_id, gear_id, page_number, num_records, db
        )
    return activities_crud.get_user_activities_by_gear_id_and_user_id(user_id, gear_id, db)


def count_gear_activities(user_id: int, gear_id: int, db: Session) -> int:
    """Count a user's activities for a gear."""
    return activities_crud.get_gear_activities_count_by_user_id(user_id, gear_id, db)


def list_user_activities_paginated(
    user_id: int,
    requester_user_id: int,
    page_number: int,
    num_records: int,
    db: Session,
    *,
    activity_type: int | None = None,
    start_date: date | None = None,
    end_date: date | None = None,
    name_search: str | None = None,
    sort_by: str | None = None,
    sort_order: str | None = None,
) -> list[activities_schema.Activity] | None:
    """List a user's activities (filtered, paginated) scoped to the requester.

    The owner sees all of their activities; any other requester sees only the
    ones visible to them (the CRUD layer applies the mask from ``user_is_owner``
    plus the requester id).
    """
    activities = activities_crud.get_user_activities_with_pagination(
        user_id=user_id,
        db=db,
        page_number=page_number,
        num_records=num_records,
        activity_type=activity_type,
        start_date=start_date,
        end_date=end_date,
        name_search=name_search,
        sort_by=sort_by,
        sort_order=sort_order,
        user_is_owner=(user_id == requester_user_id),
        followee_ids=_followees_of(requester_user_id, db),
    )
    logger.debug(
        "Listed paginated user activities",
        extra=core_logger.context(
            user_id=user_id,
            requester_user_id=requester_user_id,
            page_number=page_number,
            page_size=num_records,
            returned=len(activities) if activities else 0,
        ),
    )
    return activities


def _require_feed_owner(user_id: int, requester_user_id: int) -> None:
    """Enforce that the requester is reading their own following feed (OWASP A01 / IDOR)."""
    if user_id != requester_user_id:
        logger.warning(
            "Blocked following-feed access for a feed the caller does not own",
            extra=core_logger.context(requester_user_id=requester_user_id, user_id=user_id),
        )
        raise core_exceptions.PermissionDeniedError()


# ---------------------------------------------------------------------------
# Paged reads
#
# Each of these resolves a page and its total together so the API can answer in
# one round trip. The two queries still run, but the client no longer has to
# repeat its filters on a second request and hope the count still matches.
# ---------------------------------------------------------------------------


def page_user_activities(
    user_id: int,
    requester_user_id: int,
    page_number: int,
    num_records: int,
    db: Session,
    *,
    activity_type: int | None = None,
    start_date: date | None = None,
    end_date: date | None = None,
    name_search: str | None = None,
    sort_by: str | None = None,
    sort_order: str | None = None,
) -> activities_schema.ActivityPage:
    """Return one page of a user's activities together with the matching total.

    Args:
        user_id: The owner whose activities to list.
        requester_user_id: The authenticated caller, used to scope visibility.
        page_number: 1-based page number.
        num_records: Page size.
        db: Database session.
        activity_type: Optional sport-type filter.
        start_date: Optional inclusive start date filter.
        end_date: Optional inclusive end date filter.
        name_search: Optional case-insensitive name search.
        sort_by: Optional sort field.
        sort_order: Optional sort direction.

    Returns:
        The page envelope. ``total`` carries the same filters and the same
        visibility scoping as ``items``.
    """
    items = list_user_activities_paginated(
        user_id,
        requester_user_id,
        page_number,
        num_records,
        db,
        activity_type=activity_type,
        start_date=start_date,
        end_date=end_date,
        name_search=name_search,
        sort_by=sort_by,
        sort_order=sort_order,
    )
    total = activities_crud.count_user_activities(
        user_id=user_id,
        db=db,
        activity_type=activity_type,
        start_date=start_date,
        end_date=end_date,
        name_search=name_search,
        user_is_owner=(user_id == requester_user_id),
        followee_ids=_followees_of(requester_user_id, db),
    )
    return activities_schema.ActivityPage.build(items, total, page_number, num_records)


def scroll_following_feed(
    user_id: int,
    requester_user_id: int,
    cursor: str | None,
    num_records: int,
    db: Session,
) -> activities_schema.ActivityFeedPage:
    """Return one keyset slice of the requester's following feed.

    Args:
        user_id: The feed owner (must be the requester).
        requester_user_id: The authenticated caller.
        cursor: Opaque cursor from the previous slice, or ``None`` to start.
        num_records: Slice size.
        db: Database session.

    Returns:
        The slice plus the cursor for the next one.
    """
    _require_feed_owner(user_id, requester_user_id)
    followee_ids = followers_integration.list_accepted_followee_ids(requester_user_id, db)
    after = core_pagination.decode_cursor(cursor) if cursor else None
    # Over-fetch by one: the extra row proves another slice exists without a
    # second query, and is dropped before serialising.
    entries = activities_crud.get_following_feed_after(followee_ids, after, num_records + 1, db)
    has_more = len(entries) > num_records
    page_entries = entries[:num_records]
    items = [entry.activity for entry in page_entries]
    next_cursor = (
        core_pagination.encode_cursor(page_entries[-1].cursor_start_time, page_entries[-1].cursor_id)
        if has_more and page_entries
        else None
    )
    logger.debug(
        "Built following feed slice",
        extra=core_logger.context(
            requester_user_id=requester_user_id,
            followee_count=len(followee_ids) if followee_ids else 0,
            returned=len(items),
            has_more=has_more,
        ),
    )
    return activities_schema.ActivityFeedPage(items=items, num_records=num_records, next_cursor=next_cursor)


def page_gear_activities(
    user_id: int,
    gear_id: int,
    page_number: int,
    num_records: int,
    db: Session,
) -> activities_schema.ActivityPage:
    """Return one page of a user's activities for a gear with the matching total.

    Args:
        user_id: The owner whose activities to list.
        gear_id: The gear to filter by.
        page_number: 1-based page number.
        num_records: Page size.
        db: Database session.

    Returns:
        The page envelope.
    """
    items = list_gear_activities(user_id, gear_id, page_number, num_records, db)
    total = count_gear_activities(user_id, gear_id, db)
    return activities_schema.ActivityPage.build(items, total, page_number, num_records)


# ---------------------------------------------------------------------------
# Single-activity reads and writes
# ---------------------------------------------------------------------------


def list_activity_types(user_id: int, db: Session) -> dict[int, str]:
    """Return the distinct activity types a user has recorded, keyed by type code."""
    return activities_crud.get_distinct_activity_types_for_user(user_id, db)


def get_activity(activity_id: int, requester_user_id: int, db: Session) -> activities_schema.Activity:
    """Return an activity the requester owns or is permitted to see.

    Args:
        activity_id: The activity to read.
        requester_user_id: The authenticated caller.
        db: Database session.

    Returns:
        The activity, visibility-masked for a non-owner.

    Raises:
        NotFoundError: When the activity does not exist or is not visible to the
            caller — indistinguishable on purpose, so the endpoint cannot be used
            to enumerate activity ids.
    """
    activity = activities_crud.get_activity_by_id_from_user_id_or_has_visibility(
        activity_id, requester_user_id, db, _followees_of(requester_user_id, db)
    )
    if activity is None:
        logger.debug(
            "Activity read resolved to nothing visible",
            extra=core_logger.context(activity_id=activity_id, requester_user_id=requester_user_id),
        )
        raise core_exceptions.NotFoundError(f"Activity {activity_id} not found")
    return activity


def get_public_activity(activity_id: int, db: Session) -> activities_schema.Activity:
    """Return a publicly shared activity.

    Args:
        activity_id: The activity to read.
        db: Database session.

    Returns:
        The activity.

    Raises:
        NotFoundError: When the activity does not exist or is not public.
    """
    if not server_settings_integration.public_shareable_links_enabled(db):
        raise core_exceptions.NotFoundError("Activity not found")
    activity = activities_crud.get_activity_by_id_if_is_public(activity_id, db)
    if activity is None:
        raise core_exceptions.NotFoundError("Activity not found")
    return activity


def edit_activity(
    activity_id: int,
    user_id: int,
    activity_attributes: activities_schema.ActivityEdit,
    db: Session,
    if_match: str | None = None,
) -> activities_schema.Activity:
    """Apply partial updates to one of the user's activities.

    The update is staged (``commit=False``) and the publisher owns the single
    commit, so when durable jobs are enabled the ``activity.updated`` outbox row
    is written in the *same* transaction as the change — a consumer can never see
    a row that changed without the fact that it did.
    """
    logger.debug(
        "Editing an activity",
        extra=core_logger.context(activity_id=activity_id, user_id=user_id),
    )
    if if_match is not None:
        current = activities_crud.get_activity_by_id_from_user_id(activity_id, user_id, db)
        core_etag.require_if_match(if_match, current.version if current else None)
    # Only the fields the client actually sent; the CRUD applies the same set.
    changed_fields = [field for field in activity_attributes.model_dump(exclude_unset=True) if field != "id"]
    try:
        updated = activities_crud.edit_activity(user_id, activity_id, activity_attributes, db, commit=False)
    except StaleDataError as err:
        # The row changed between the precondition check and the flush, so the
        # check alone would have let this write through.
        db.rollback()
        logger.warning(
            "Rejected a stale activity edit",
            extra=core_logger.context(activity_id=activity_id, user_id=user_id),
        )
        raise core_exceptions.PreconditionFailedError(
            "The activity was modified by someone else; re-read it and retry"
        ) from err
    activity_event_publishers.publish_activity_updated(
        activity_id,
        user_id,
        changed_fields,
        db=db,
        commit=db.commit,
    )
    logger.info(
        "Edited an activity",
        extra=core_logger.context(activity_id=activity_id, user_id=user_id, changed_fields=sorted(changed_fields)),
    )
    return updated


def bulk_edit_activities(
    user_id: int,
    body: activities_schema.ActivitiesBulkEdit,
    db: Session,
) -> int:
    """Apply a bulk edit across all of the user's activities.

    Publishes one ``activity.updated`` per changed row, atomically with the
    update, so a consumer of the single-activity edit needs no separate handling
    for the bulk one — the fact is identical either way.

    Args:
        user_id: The owner whose activities to edit.
        body: The fields to apply; only those present are changed.
        db: Database session.

    Returns:
        How many activities changed.

    Raises:
        InvalidInputError: When the body asks for no change at all. An empty
            patch is a client bug, not a no-op worth reporting as success.
    """
    if body.visibility is None:
        raise core_exceptions.InvalidInputError("No supported field to update was provided")

    updated_ids = activities_crud.edit_user_activities_visibility(user_id, body.visibility, db, commit=False)
    activity_event_publishers.publish_activities_updated(
        updated_ids,
        user_id,
        ["visibility"],
        db,
        db.commit,
        source="api:bulk_edit_activities",
    )
    logger.info(
        "Bulk-edited activity visibility",
        extra=core_logger.context(user_id=user_id, visibility=body.visibility, updated=len(updated_ids)),
    )
    return len(updated_ids)


def delete_activity(activity_id: int, user_id: int, db: Session) -> None:
    """Delete one of the user's activities and publish ``activity.deleted``.

    The delete is staged (``commit=False``) and the publisher owns the single
    commit, so when durable jobs are enabled the outbox row is written in the
    *same* transaction as the delete. A crash can no longer leave the row deleted
    but the cleanup event unpublished, which would orphan the thumbnail and
    source-file blobs. On the best-effort path the commit runs first and a
    bus-dispatch failure is swallowed.

    Ownership lives in the delete's ``WHERE`` clause (404 when the activity is
    missing *or* owned by someone else), so there is no read-then-delete gap and
    no caller-side precondition to forget.

    Args:
        activity_id: The activity to delete.
        user_id: The authenticated owner.
        db: Database session.

    Returns:
        None.
    """
    activities_crud.delete_activity(activity_id, user_id, db, commit=False)
    activity_event_publishers.publish_activity_deleted(activity_id, user_id, db, commit=db.commit)
    logger.info(
        "Deleted an activity",
        extra=core_logger.context(activity_id=activity_id, user_id=user_id),
    )


def bulk_set_activities_gear(
    user_id: int,
    gear_assignments: dict[int, int | None],
    db: Session,
    *,
    source: str,
) -> int:
    """Assign gear to many of a user's activities at once.

    Publishes one ``activity.updated`` per changed row, atomically with the
    updates. A provider re-syncing gear mutates activities from outside the
    activities module, so without the event a consumer would see the same silent
    change bulk deletes used to make.

    Args:
        user_id: The owning user id (ownership is enforced by the update).
        gear_assignments: Map of activity id -> gear id (or ``None`` to clear).
        db: Database session.
        source: The caller recorded on the published events.

    Returns:
        The number of activities updated.
    """
    updated_ids = activities_crud.bulk_set_activities_gear_id(user_id, gear_assignments, db, commit=False)
    activity_event_publishers.publish_activities_updated(
        updated_ids,
        user_id,
        ["gear_id"],
        db,
        db.commit,
        source=source,
    )
    logger.info(
        "Bulk-assigned gear to activities",
        extra=core_logger.context(user_id=user_id, requested=len(gear_assignments), updated=len(updated_ids)),
    )
    return len(updated_ids)


def delete_all_strava_activities(user_id: int, db: Session, *, source: str) -> int:
    """Delete all of a user's Strava-sourced activities.

    Emits one ``activity.deleted`` per removed activity, atomically with the
    deletes, so the thumbnail and source-file cleanup subscribers reclaim the
    blobs each activity owned. Without it the rows vanished silently and their
    artifacts were orphaned in storage permanently.

    Args:
        user_id: The owning user id.
        db: Database session.
        source: The caller recorded on the published events.

    Returns:
        The number of activities deleted.
    """
    deleted_ids = activities_crud.delete_all_strava_activities_for_user(user_id, db, commit=False)
    activity_event_publishers.publish_activities_deleted(deleted_ids, user_id, db, db.commit, source=source)
    # Irreversible and triggered from another module, so the count is recorded
    # here rather than left to the caller.
    logger.info(
        "Deleted all Strava-sourced activities for user",
        extra=core_logger.context(user_id=user_id, deleted_count=len(deleted_ids)),
    )
    return len(deleted_ids)


def delete_all_activities_for_user(user_id: int, db: Session, *, source: str) -> int:
    """Delete every activity owned by a user, emitting cleanup events.

    The account-deletion path. Deleting the user row alone would let the database
    FK cascade remove the activities silently, orphaning every thumbnail and
    stored source file the user ever produced — an incomplete erasure. Removing
    them explicitly first yields the ids needed to publish ``activity.deleted``,
    so the cleanup subscribers delete the blobs too.

    Args:
        user_id: The owning user id.
        db: Database session.
        source: The caller recorded on the published events.

    Returns:
        The number of activities deleted.
    """
    deleted_ids = activities_crud.delete_all_activities_for_user(user_id, db, commit=False)
    activity_event_publishers.publish_activities_deleted(deleted_ids, user_id, db, db.commit, source=source)
    logger.info(
        "Deleted all activities for user",
        extra=core_logger.context(user_id=user_id, deleted_count=len(deleted_ids)),
    )
    return len(deleted_ids)


# ---------------------------------------------------------------------------
# Derived-artifact maintenance
#
# The sibling surface: the thumbnail, geocoding and media subsystems reach the
# activity row through these instead of importing ``activity.crud``. Each is a
# system-level operation with no requester to authorize — the derived work runs
# detached from any request — which is why they carry no access check and why
# they are not on ``integration_service``: no *other module* has any business
# setting a thumbnail key.


def owns_activity(activity_id: int, user_id: int, db: Session) -> bool:
    """Return whether the user owns the activity.

    Args:
        activity_id: The activity to check.
        user_id: The claimed owner.
        db: Database session.

    Returns:
        True when the activity exists and belongs to the user.
    """
    return activities_crud.get_activity_by_id_from_user_id(activity_id, user_id, db) is not None


def set_thumbnail_key(activity_id: int, key: str | None, db: Session) -> None:
    """Record (or clear) an activity's stored map-thumbnail key.

    Args:
        activity_id: The activity whose thumbnail was rendered or removed.
        key: The stored key, or ``None`` to clear it.
        db: Database session.

    Returns:
        None.
    """
    activities_crud.set_activity_thumbnail_path(activity_id, key, db)


def clear_all_thumbnail_keys(db: Session) -> None:
    """Clear the stored thumbnail key on every activity.

    Args:
        db: Database session.

    Returns:
        None.
    """
    activities_crud.clear_all_activity_thumbnail_paths(db)


def list_activities_with_thumbnail(db: Session) -> list[activities_contracts.ActivityThumbnailRef]:
    """Return references to every activity that has a stored thumbnail.

    Args:
        db: Database session.

    Returns:
        Thumbnail references (id + stored key).
    """
    return activities_crud.get_activities_with_thumbnail(db)


def list_activities_without_thumbnail(db: Session) -> list[activities_contracts.ActivityThumbnailRef]:
    """Return references to every activity that has no stored thumbnail.

    Args:
        db: Database session.

    Returns:
        Thumbnail references (id, with a null key).
    """
    return activities_crud.get_activities_without_thumbnail(db)


def list_activities_missing_location(
    db: Session,
    limit: int = 200,
) -> list[activities_contracts.ActivityLocationRef]:
    """Return references to activities with no reverse-geocoded location yet.

    Args:
        db: Database session.
        limit: Maximum number of candidates, bounding one backfill pass.

    Returns:
        Location references (id only).
    """
    return activities_crud.get_activities_missing_location(db, limit)


def set_activity_location(
    activity_id: int,
    city: str | None,
    town: str | None,
    country: str | None,
    db: Session,
) -> bool:
    """Persist a reverse-geocoded location on an activity.

    Args:
        activity_id: The activity the location was resolved for.
        city: Resolved city, or ``None``.
        town: Resolved town, or ``None``.
        country: Resolved country, or ``None``.
        db: Database session.

    Returns:
        True when the activity existed and was updated.
    """
    return activities_crud.update_activity_location(activity_id, city, town, country, db)
