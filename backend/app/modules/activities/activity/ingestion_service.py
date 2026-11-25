"""Core activity ingestion — persist a canonical :class:`ParsedActivity`.

This is the seam that makes parsing irrelevant to the activities core. It accepts
a format-agnostic :class:`~modules.activities.activity.contracts.ParsedActivity`,
persists its contributed components, and publishes ``activity.created``.
"""

import uuid
from datetime import datetime

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

import core.exceptions as core_exceptions
import core.logger as core_logger
import modules.activities.activity.constants as activity_constants
import modules.activities.activity.contracts as activity_contracts
import modules.activities.activity.crud as activity_crud
import modules.activities.activity.event_publishers as activity_event_publishers
import modules.activities.activity.schema as activity_schema
import modules.activities.contributor_registry as activities_contributor_registry
import modules.activities.contributors as activities_contributors

logger = core_logger.get_logger(__name__)


def _derive_dedup_key(
    activity: activity_schema.ActivityBase | activity_contracts.ActivityCore,
    source: activity_contracts.ImportSource | None,
    *,
    salt_with_start: bool = True,
) -> str | None:
    """Derive a stable idempotency key for an activity.

    Precedence:

    1. **Provider id** — Strava then Garmin Connect (both on the core ``Activity``
       schema). Provider ids are stable across server-side re-processing/edits, so
       they are the canonical identity for provider syncs. Garmin ids are salted
       with the start time because one multi-activity Garmin ``.fit`` splits into
       several activities that all carry the *same* Garmin activity id — without
       the salt every activity after the first was silently discarded as an
       already-ingested duplicate.
    2. **File content hash** — for file-based sources (upload / bulk import) that
       carry no provider id, ``source.content_hash`` (the SHA-256 of the parsed
       file) plus the activity's start time. The start-time salt keeps multiple
       activities parsed from one multi-activity ``.fit`` (which share a file
       hash) distinct.
    3. ``None`` — nothing to key on; ``create_activity`` falls back to start-time
       dedup (marks a duplicate hidden rather than a no-op).

    A multisport activity is the only one of its file, so its key leaves out the
    start-time salt (``salt_with_start=False``): ``garmin:<id>`` and ``file:<sha256>``.

    Stays free of any file-format or provider-module coupling: it reads only the
    core schema + the ``ImportSource`` contract.

    Args:
        activity: The parsed activity schema.
        source: Where the activity came from, or None.
        salt_with_start: Whether a Garmin or file key carries the start time.

    Returns:
        The key, or None when there is nothing to key on.
    """
    if activity.strava_activity_id is not None:
        return f"strava:{activity.strava_activity_id}"
    if activity.garminconnect_activity_id is not None:
        if not salt_with_start or not isinstance(activity.start_time, datetime):
            return f"garmin:{activity.garminconnect_activity_id}"
        return f"garmin:{activity.garminconnect_activity_id}:{int(activity.start_time.timestamp())}"
    if source is not None and source.content_hash:
        if not salt_with_start:
            return f"file:{source.content_hash}"
        if isinstance(activity.start_time, datetime):
            return f"file:{source.content_hash}:{int(activity.start_time.timestamp())}"
    return None


def _dedup_key(parsed: activity_contracts.ParsedActivity, *, salt_with_start: bool = True) -> str | None:
    """Pick the idempotency key of a parsed activity: the source's explicit key, else the derived one.

    Args:
        parsed: The parsed activity.
        salt_with_start: Whether a derived Garmin or file key carries the start time.

    Returns:
        The key, or None when there is nothing to key on.
    """
    source = parsed.source
    if source is not None and source.dedup_key:
        return source.dedup_key
    return _derive_dedup_key(parsed.activity, source, salt_with_start=salt_with_start)


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
    dedup_key: str | None,
    db: Session,
    *,
    parent: activity_schema.ActivityRead | None = None,
) -> activity_schema.ActivityRead:
    """Stage an activity row, its components and ``activity.created``.

    Args:
        parsed: The parsed activity.
        component_work: The contributors and data from :func:`_component_work`.
        dedup_key: The idempotency key stored on the row.
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
        dedup_key=dedup_key,
        parent_activity_id=parent.id if parent is not None else None,
        detect_duplicate_start=parent is None,
    )

    if created_activity is None:
        logger.debug(
            "store_parsed_activity: create_activity returned no activity",
            extra=core_logger.context(user_id=parsed.activity.user_id, dedup_key=dedup_key),
        )
        raise core_exceptions.ProcessingError("Error creating activity")

    if created_activity.user_id is None:
        logger.debug(
            "store_parsed_activity: created activity has no owner",
            extra=core_logger.context(activity_id=created_activity.id, dedup_key=dedup_key),
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
    dedup_key: str | None, user_id: uuid.UUID | None, db: Session
) -> activity_schema.ActivityRead | None:
    """Look up the activity a dedup key already names.

    Args:
        dedup_key: The idempotency key, or None.
        user_id: The owner.
        db: Database session.

    Returns:
        The stored activity, or None when the key is absent or unused.
    """
    if dedup_key is None or user_id is None:
        return None
    existing = activity_crud.get_activity_by_dedup_key(dedup_key, user_id, db)
    if existing is not None:
        logger.debug(
            "Skipping re-import: dedup key already ingested",
            extra=core_logger.context(dedup_key=dedup_key, activity_id=existing.id, user_id=user_id),
        )
    return existing


def _winner_of_the_race(
    err: IntegrityError, dedup_key: str | None, user_id: uuid.UUID | None, db: Session
) -> activity_schema.ActivityRead:
    """Resolve an insert that lost the race for a dedup key: roll back and return the activity that won it.

    The pre-insert dedup check is read-then-write, so a concurrent import of the same activity can pass it and both
    inserts race. The unique index on (user_id, dedup_key) is what actually guarantees idempotency; losing that race
    means the other worker stored it, which is precisely the outcome the caller wanted.

    Args:
        err: The integrity error the insert raised.
        dedup_key: The idempotency key of the activity being stored.
        user_id: The owner.
        db: Database session.

    Returns:
        The activity that won the race.

    Raises:
        ProcessingError: When there is no key to resolve the conflict by, or the error was another constraint.
    """
    db.rollback()
    if dedup_key is None or user_id is None:
        logger.debug(
            "Integrity error storing a parsed activity: no dedup key to resolve the conflict",
            exc_info=err,
            extra=core_logger.context(user_id=user_id, dedup_key=dedup_key),
        )
        raise core_exceptions.ProcessingError("Error creating activity") from err

    winner = activity_crud.get_activity_by_dedup_key(dedup_key, user_id, db)
    if winner is None:
        # The integrity error was not the dedup race (some other constraint).
        logger.debug(
            "Integrity error storing a parsed activity: not a dedup-key race",
            exc_info=err,
            extra=core_logger.context(user_id=user_id, dedup_key=dedup_key),
        )
        raise core_exceptions.ProcessingError("Error creating activity") from err

    logger.debug(
        "Lost the insert race for dedup key; treating re-import as a no-op",
        extra=core_logger.context(dedup_key=dedup_key, activity_id=winner.id, user_id=user_id),
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
    dedup_key: str | None = None
    try:
        # Idempotency: a stable dedup_key makes re-import of an
        # already-ingested activity a true no-op. Prefer an explicit key from the
        # source, otherwise derive one from the activity's provider ids. When a
        # key is present and already stored for this owner, return the existing
        # activity without creating a duplicate row, its children, or
        # re-publishing ``activity.created``.
        dedup_key = _dedup_key(parsed)
        component_work = _component_work(parsed)
        existing = _existing_activity(dedup_key, parsed.activity.user_id, db)
        if existing is not None:
            return existing
        return _stage_activity(parsed, component_work, dedup_key, db)
    except IntegrityError as err:
        return _winner_of_the_race(err, dedup_key, parsed.activity.user_id, db)
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
    commit. The parent is keyed by the file alone (``garmin:<id>`` or ``file:<sha256>``) and each leg by the file and
    its start, as a leg was keyed before groups existed. The legs copy the parent's privacy, and only the parent looks
    for a duplicate start.

    A group already stored stages nothing and returns its parent. A file whose legs were stored on their own before
    groups existed stages nothing either and returns those legs, which a later pass can regroup.

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
    parent_key: str | None = None
    try:
        parent_key = _dedup_key(parent, salt_with_start=False)
        parent_work = _component_work(parent)
        leg_work = [(leg, _dedup_key(leg), _component_work(leg)) for leg in legs]

        existing_parent = _existing_activity(parent_key, parent.activity.user_id, db)
        if existing_parent is not None:
            return [existing_parent]
        standalone_legs = [
            existing
            for leg, key, _work in leg_work
            if (existing := _existing_activity(key, leg.activity.user_id, db)) is not None
        ]
        if standalone_legs:
            return standalone_legs

        staged_parent = _stage_activity(parent, parent_work, parent_key, db)
        for leg, key, work in leg_work:
            _stage_activity(leg, work, key, db, parent=staged_parent)
        return [staged_parent]
    except IntegrityError as err:
        return [_winner_of_the_race(err, parent_key, parent.activity.user_id, db)]
    except core_exceptions.DomainError:
        db.rollback()
        raise
