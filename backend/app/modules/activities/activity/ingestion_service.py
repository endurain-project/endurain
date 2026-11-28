"""Core activity ingestion — persist a canonical :class:`ParsedActivity`.

This is the seam that makes parsing irrelevant to the activities core. It accepts
a format-agnostic :class:`~modules.activities.activity.contracts.ParsedActivity`,
persists its contributed components, and publishes ``activity.created``.
"""

import uuid

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

import core.exceptions as core_exceptions
import core.logger as core_logger
import core.timezone as core_timezone
import modules.activities.activity.constants as activity_constants
import modules.activities.activity.contracts as activity_contracts
import modules.activities.activity.crud as activity_crud
import modules.activities.activity.event_publishers as activity_event_publishers
import modules.activities.activity.schema as activity_schema
import modules.activities.activity.source_crud as activity_source_crud
import modules.activities.computation as activities_computation
import modules.activities.contributor_registry as activities_contributor_registry
import modules.activities.contributors as activities_contributors

logger = core_logger.get_logger(__name__)


def _identity(
    parsed: activity_contracts.ParsedActivity, *, whole_file: bool = False
) -> activity_contracts.NewSource | None:
    """Pick the source an activity is identified by.

    Precedence:

    1. **Strava id**, kept as it is: a Strava activity is stored once.
    2. **Garmin Connect id.** One multi-activity ``.fit`` splits into several activities that all carry the same Garmin
       id, so the id is paired with the recording's start, whole seconds. Without the start every activity after the
       first would be discarded as already stored.
    3. **File hash**, for file sources that carry no provider id (upload, bulk import), paired with the start for the
       same reason.
    4. ``None`` when there is nothing to identify the activity by; it is stored without a source.

    A multisport activity is the only one of its file, so its source stands for the whole file and has no start
    (``whole_file=True``).

    Stays free of any file-format or provider-module coupling: it reads only the core schema and the ``ImportSource``
    contract.

    Args:
        parsed: The parsed activity.
        whole_file: Whether the source stands for the whole file.

    Returns:
        The source to store with the activity, or ``None``.
    """
    activity = parsed.activity
    source = parsed.source
    start = core_timezone.to_utc_aware(activity.start_time)
    session_start = None if whole_file or start is None else activity_source_crud.floor_to_second(start)
    if activity.strava_activity_id is not None:
        return activity_contracts.NewSource(
            activity_constants.SOURCE_KIND_STRAVA,
            activity.strava_activity_id,
            None,
            None,
            activity_constants.SOURCE_PRECEDENCE_API,
        )
    if activity.garminconnect_activity_id is not None:
        return activity_contracts.NewSource(
            activity_constants.SOURCE_KIND_GARMIN,
            activity.garminconnect_activity_id,
            None,
            session_start,
            activity_constants.SOURCE_PRECEDENCE_DEVICE_FILE,
        )
    if source is not None and source.content_hash and (whole_file or session_start is not None):
        return activity_contracts.NewSource(
            activity_constants.SOURCE_KIND_FILE, None, source.content_hash, session_start, source.precedence
        )
    return None


def parent_source(parsed: activity_contracts.ParsedActivity) -> activity_contracts.NewSource | None:
    """Pick the source of a multisport activity: the file's alone, with no start.

    Args:
        parsed: The parsed multisport activity.

    Returns:
        The source, or ``None`` when there is nothing to identify the activity by.
    """
    return _identity(parsed, whole_file=True)


def _component_work(
    parsed: activity_contracts.ParsedActivity,
) -> list[tuple[activities_contributors.ActivityIngestionContributor, object]]:
    """Resolve the contributor of each parsed component, before anything is stored.

    Args:
        parsed: The parsed activity.

    Returns:
        The contributor and data of each component that has data.

    Raises:
        ProcessingError: When a component has no registered contributor, so no parsed data is dropped silently.
    """
    work = []
    for key, data in parsed.components.items():
        if data is None:
            continue
        contributor = activities_contributor_registry.get_activity_ingestion_contributor(key)
        if contributor is None:
            logger.debug(
                "No activity ingestion contributor is registered for a parsed component",
                extra=core_logger.context(component=key),
            )
            raise core_exceptions.ProcessingError()
        work.append((contributor, data))
    return work


def _stage_activity(
    parsed: activity_contracts.ParsedActivity,
    component_work: list[tuple[activities_contributors.ActivityIngestionContributor, object]],
    identity: activity_contracts.NewSource | None,
    db: Session,
    *,
    parent: activity_schema.ActivityRead | None = None,
) -> activity_schema.ActivityRead:
    """Stage an activity row, its components and ``activity.created``.

    Args:
        parsed: The parsed activity.
        component_work: The contributors and data from :func:`_component_work`.
        identity: The source stored with the activity, ``None`` for an activity with nothing to identify it.
        db: Database session.
        parent: The stored multisport activity the new activity is a leg of. The leg takes the parent's privacy
            fields and does not look for a same-start duplicate of its own.

    Returns:
        The staged activity.

    Raises:
        ProcessingError: When the activity could not be created.
    """
    source = parsed.source
    activity = parsed.activity
    if parent is not None:
        activity = activity.model_copy(
            update={field: getattr(parent, field) for field in activity_constants.PRIVACY_FIELDS}
        )
    created_activity = activity_crud.create_activity(
        activity,
        db,
        source=identity,
        parent_activity_id=parent.id if parent is not None else None,
        detect_duplicate_start=parent is None,
        analysis_version=activities_computation.ANALYSIS_VERSION,
        file_id=source.retained_file_id if source is not None and parent is None else None,
    )

    if created_activity is None:
        logger.debug(
            "store_parsed_activity: create_activity returned no activity",
            extra=core_logger.context(user_id=parsed.activity.user_id),
        )
        raise core_exceptions.ProcessingError("Error creating activity")

    if created_activity.user_id is None:
        logger.debug(
            "store_parsed_activity: created activity has no owner",
            extra=core_logger.context(activity_id=created_activity.id),
        )
        raise core_exceptions.ProcessingError("Error creating activity")

    source_kind = source.kind if source is not None else "unknown"
    logger.debug(
        "Created activity from parsed file",
        extra=core_logger.context(
            activity_id=created_activity.id,
            user_id=created_activity.user_id,
            source_kind=source_kind,
        ),
    )

    # Contributors only stage, so the parent and children land in one
    # transaction. Unknown keys fail closed before this rather
    # than silently dropping parsed data.
    for contributor, data in component_work:
        contributor.persist(data, created_activity, db)

    logger.debug(
        "Stored parsed activity components",
        extra=core_logger.context(
            activity_id=created_activity.id,
            component_keys=tuple(contributor.key for contributor, _data in component_work),
        ),
    )

    # Stage the domain fact with the rows. Derived work reacts by subscribing to
    # ``activity.created``; this service has no knowledge of what consumes it.
    # When durable jobs are enabled the outbox row joins the caller's
    # transaction and commits with the domain rows; otherwise the event
    # dispatches on the bus after the caller's commit (best-effort — the stored
    # activity is the source of truth).
    activity_event_publishers.publish_activity_created(
        created_activity.id,
        created_activity.user_id,
        duplicate_start_time=parent is None and created_activity.is_hidden,
        db=db,
        source=f"ingest:{source_kind}",
        parent_activity_id=created_activity.parent_activity_id,
    )
    return created_activity


def _existing_activity(
    identity: activity_contracts.NewSource | None, user_id: uuid.UUID | None, db: Session
) -> activity_schema.ActivityRead | None:
    """Look up the activity a source identity already belongs to.

    Args:
        identity: The source identity, or None.
        user_id: The owner.
        db: Database session.

    Returns:
        The stored activity, or None when there is no identity or it is unused.
    """
    if identity is None or user_id is None:
        return None
    activity_id = activity_source_crud.get_activity_id_by_source(user_id, identity, db)
    existing = activity_crud.get_activity_by_id(activity_id, db) if activity_id is not None else None
    if existing is not None:
        logger.debug(
            "Skipping re-import: source already ingested",
            extra=core_logger.context(source_kind=identity.kind, activity_id=existing.id, user_id=user_id),
        )
    return existing


def _winner_of_the_race(
    err: IntegrityError, identity: activity_contracts.NewSource | None, user_id: uuid.UUID | None, db: Session
) -> activity_schema.ActivityRead:
    """Resolve an insert that lost the race for a source identity: roll back and return the activity that won it.

    The pre-insert lookup is read-then-write, so a concurrent import of the same activity can pass it and both
    inserts race. The unique indexes on ``activity_sources`` are what actually guarantee idempotency; losing that race
    means the other worker stored it, which is precisely the outcome the caller wanted.

    Args:
        err: The integrity error the insert raised.
        identity: The source identity of the activity being stored.
        user_id: The owner.
        db: Database session.

    Returns:
        The activity that won the race.

    Raises:
        ProcessingError: When there is no identity to resolve the conflict by, or the error was another constraint.
    """
    db.rollback()
    if identity is None or user_id is None:
        logger.debug(
            "Integrity error storing a parsed activity: no source to resolve the conflict",
            exc_info=err,
            extra=core_logger.context(user_id=user_id),
        )
        raise core_exceptions.ProcessingError("Error creating activity") from err

    winner = _existing_activity(identity, user_id, db)
    if winner is None:
        # The integrity error was not the source race (some other constraint).
        logger.debug(
            "Integrity error storing a parsed activity: not a source race",
            exc_info=err,
            extra=core_logger.context(user_id=user_id, source_kind=identity.kind),
        )
        raise core_exceptions.ProcessingError("Error creating activity") from err

    logger.debug(
        "Lost the insert race for a source; treating re-import as a no-op",
        extra=core_logger.context(source_kind=identity.kind, activity_id=winner.id, user_id=user_id),
    )
    return winner


def store_parsed_activity(
    parsed: activity_contracts.ParsedActivity,
    db: Session,
) -> activity_schema.ActivityRead:
    """Stage a parsed activity, its children and ``activity.created``.

    Nothing is committed: the caller commits, and the event follows that commit.
    A re-import of an already stored activity stages nothing.

    Args:
        parsed: The canonical parsed activity to store.
        db: Database session.

    Returns:
        The created activity schema (with generated id / ``created_at``).

    Raises:
        ProcessingError: When the activity could not be created.
    """
    # Bound before the try so the IntegrityError handler can always read it.
    identity: activity_contracts.NewSource | None = None
    try:
        # Idempotency: the activity's source identity (its provider id or its file's hash) makes re-import of an
        # already-ingested activity a true no-op. When the owner already holds the identity, return the existing
        # activity without creating a duplicate row, its children, or re-publishing ``activity.created``.
        identity = _identity(parsed)
        component_work = _component_work(parsed)
        existing = _existing_activity(identity, parsed.activity.user_id, db)
        if existing is not None:
            return existing
        return _stage_activity(parsed, component_work, identity, db)
    except IntegrityError as err:
        return _winner_of_the_race(err, identity, parsed.activity.user_id, db)
    except core_exceptions.DomainError:
        # Roll back the in-flight unit of work so no partial rows survive and the
        # session stays clean for the caller (bulk import reuses one session).
        # Caught only to clean up — this layer never constructs the error, and
        # never decides its status.
        db.rollback()
        raise


def store_parsed_group(
    parent: activity_contracts.ParsedActivity,
    legs: list[activity_contracts.ParsedActivity],
    db: Session,
) -> list[activity_schema.ActivityRead]:
    """Stage a multisport activity with its legs in one unit of work.

    Nothing is committed: the caller commits once, so the group lands whole or not at all, and the events follow that
    commit. The parent holds the file's source, a Garmin id or a file hash with no start, and each leg the source of its
    own session, with its start. The legs copy the parent's privacy, and only the parent looks for a duplicate start.

    A group already stored stages nothing and returns its parent, also when another import committed it between this
    one's look for the parent and its look for the legs. A file whose legs were stored on their own before groups
    existed stages nothing either and returns those legs, which a later pass can regroup.

    Args:
        parent: The multisport activity.
        legs: Its legs, in time order.
        db: Database session.

    Returns:
        The activities the athlete sees: the stored parent, or the legs found stored on their own.

    Raises:
        ProcessingError: When an activity could not be created.
    """
    # Bound before the try so the IntegrityError handler can always read it.
    parent_identity: activity_contracts.NewSource | None = None
    try:
        parent_identity = parent_source(parent)
        parent_work = _component_work(parent)
        leg_work = [(leg, _identity(leg), _component_work(leg)) for leg in legs]

        existing_parent = _existing_activity(parent_identity, parent.activity.user_id, db)
        if existing_parent is not None:
            return [existing_parent]
        # A leg holds the source of its session, so legs stored on their own before groups existed are found too.
        stored_legs = [
            existing
            for leg, identity, _work in leg_work
            if (existing := _existing_activity(identity, leg.activity.user_id, db)) is not None
        ]
        # A stored leg with a parent is a group another import committed after this one looked for the parent.
        stored_parent_id = next((leg.parent_activity_id for leg in stored_legs if leg.parent_activity_id), None)
        if stored_parent_id is not None:
            stored_parent = activity_crud.get_activity_by_id(stored_parent_id, db)
            return [stored_parent] if stored_parent is not None else []
        if stored_legs:
            return stored_legs

        staged_parent = _stage_activity(parent, parent_work, parent_identity, db)
        for leg, leg_identity, work in leg_work:
            _stage_activity(leg, work, leg_identity, db, parent=staged_parent)
        return [staged_parent]
    except IntegrityError as err:
        return [_winner_of_the_race(err, parent_identity, parent.activity.user_id, db)]
    except core_exceptions.DomainError:
        db.rollback()
        raise
