"""Core activity ingestion — persist a canonical :class:`ParsedActivity`.

This is the seam that makes parsing irrelevant to the activities core. It accepts
a format-agnostic :class:`~modules.activities.activity.contracts.ParsedActivity`,
persists its contributed components, and publishes ``activity.created``.
"""

from datetime import datetime

from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

import core.exceptions as core_exceptions
import core.logger as core_logger
import modules.activities.activity.contracts as activities_contracts
import modules.activities.activity.crud as activities_crud
import modules.activities.activity.event_publishers as activity_event_publishers
import modules.activities.activity.schema as activities_schema
import modules.activities.contributor_registry as contributor_registry

logger = core_logger.get_logger(__name__)


def _derive_dedup_key(
    activity: activities_schema.ActivityBase,
    source: activities_contracts.ImportSource | None,
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

    Stays free of any file-format or provider-module coupling: it reads only the
    core schema + the ``ImportSource`` contract.
    """
    if activity.strava_activity_id is not None:
        return f"strava:{activity.strava_activity_id}"
    if activity.garminconnect_activity_id is not None:
        if not isinstance(activity.start_time, datetime):
            return f"garmin:{activity.garminconnect_activity_id}"
        return f"garmin:{activity.garminconnect_activity_id}:{int(activity.start_time.timestamp())}"
    if source is not None and source.content_hash and isinstance(activity.start_time, datetime):
        return f"file:{source.content_hash}:{int(activity.start_time.timestamp())}"
    return None


def store_parsed_activity(
    parsed: activities_contracts.ParsedActivity,
    db: Session,
) -> activities_schema.Activity:
    """Persist a parsed activity and its children, then publish ``activity.created``.

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
        source = parsed.source
        dedup_key = (
            source.dedup_key if source is not None and source.dedup_key else _derive_dedup_key(parsed.activity, source)
        )

        component_work = []
        for key, data in parsed.components.items():
            if data is None:
                continue
            contributor = contributor_registry.get_activity_ingestion_contributor(key)
            if contributor is None:
                raise core_exceptions.ProcessingError(f"No activity ingestion contributor registered for '{key}'")
            component_work.append((contributor, data))

        if dedup_key is not None and parsed.activity.user_id is not None:
            existing = activities_crud.get_activity_by_dedup_key(dedup_key, parsed.activity.user_id, db)
            if existing is not None:
                logger.info(
                    "Skipping re-import: dedup key already ingested",
                    extra=core_logger.context(
                        dedup_key=dedup_key,
                        activity_id=existing.id,
                        user_id=parsed.activity.user_id,
                    ),
                )
                return existing

        created_activity = activities_crud.create_activity(parsed.activity, db, commit=False, dedup_key=dedup_key)

        if created_activity is None or created_activity.id is None:
            logger.error(
                "store_parsed_activity: create_activity returned no activity",
                extra=core_logger.context(user_id=parsed.activity.user_id, dedup_key=dedup_key),
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

        # Persist every contributed component with commit=False so the parent and
        # children land in one transaction. Unknown keys fail closed above rather
        # than silently dropping parsed data.
        for contributor, data in component_work:
            contributor.persist(data, created_activity, db, commit=False)

        logger.debug(
            "Stored parsed activity components",
            extra=core_logger.context(
                activity_id=created_activity.id,
                component_keys=tuple(contributor.key for contributor, _data in component_work),
            ),
        )

        # Publish the domain fact and commit the unit of work atomically. Derived
        # work reacts by subscribing to ``activity.created``; this service has no
        # knowledge of what consumes it. ``publish_activity_created`` owns the
        # commit ordering (via ``commit=db.commit``): when durable jobs are enabled
        # the outbox row joins this transaction and commits with the domain rows;
        # otherwise the domain commits first and the event dispatches on the bus
        # post-commit (best-effort — the stored activity is the source of truth).
        activity_event_publishers.publish_activity_created(
            created_activity.id,
            created_activity.user_id,
            duplicate_start_time=created_activity.is_hidden,
            db=db,
            commit=db.commit,
        )

        return created_activity
    except IntegrityError as err:
        # The pre-insert dedup check above is read-then-write, so a concurrent
        # import of the same activity can pass it and both inserts race. The
        # unique index on (user_id, dedup_key) is what actually guarantees
        # idempotency; losing that race means the other worker stored it, which
        # is precisely the outcome the caller wanted. Roll back and return the
        # winner rather than surfacing a 500 for a successful import.
        db.rollback()
        if dedup_key is None or parsed.activity.user_id is None:
            logger.error(
                "Error in store_parsed_activity",
                exc_info=err,
                extra=core_logger.context(user_id=parsed.activity.user_id, dedup_key=dedup_key),
            )
            raise core_exceptions.ProcessingError("Error creating activity") from err

        winner = activities_crud.get_activity_by_dedup_key(dedup_key, parsed.activity.user_id, db)
        if winner is None:
            # The integrity error was not the dedup race (some other constraint).
            logger.error(
                "Error in store_parsed_activity",
                exc_info=err,
                extra=core_logger.context(user_id=parsed.activity.user_id, dedup_key=dedup_key),
            )
            raise core_exceptions.ProcessingError("Error creating activity") from err

        logger.info(
            "Lost the insert race for dedup key; treating re-import as a no-op",
            extra=core_logger.context(
                dedup_key=dedup_key,
                activity_id=winner.id,
                user_id=parsed.activity.user_id,
            ),
        )
        return winner
    except core_exceptions.DomainError:
        # Roll back the in-flight unit of work so no partial rows survive and the
        # session stays clean for the caller (bulk import reuses one session).
        # Caught only to clean up — this layer never constructs the error, and
        # never decides its status.
        db.rollback()
        raise
    except SQLAlchemyError as err:
        db.rollback()
        logger.error(
            "Error in store_parsed_activity",
            exc_info=err,
            extra=core_logger.context(user_id=parsed.activity.user_id, dedup_key=dedup_key),
        )
        raise core_exceptions.ProcessingError("Error creating activity") from err
