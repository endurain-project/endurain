"""Recompute stored activities from a parsed file: the shared steps of a reprocess and of a better source.

A reprocess runs a retained file through today's parsers again; a better source is a file, just parsed, of an effort
the owner already has. Both write the same things over a stored activity: its derived columns, its streams, laps,
sets and workout steps, and clear a map thumbnail whose route changed. They differ in what else changes and who owns the
transaction, so the steps are here and the two callers stay apart: the reprocess imports the pipeline to parse, the
pipeline imports this to recompute, and neither imports the other.

The recompute of an activity from a better source (:func:`stage_recompute`) runs on the pipeline's own session,
under the owner's matching lock, and the pipeline commits. It publishes no event and writes no audit row, as the
reprocess does: the activity is not new, and a client refetches by ``updated_at``.
"""

import uuid
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy.orm import Session

import core.database as core_database
import core.exceptions as core_exceptions
import core.logger as core_logger
import core.timezone as core_timezone
import modules.activities.activity.contracts as activity_contracts
import modules.activities.activity.integration_service as activity_integration
import modules.activities.activity.schema as activity_schema
import modules.activities.activity_file_storage.integration_service as activity_file_storage_integration
import modules.activities.activity_streams.integration_service as activity_streams_integration
import modules.activities.computation as activities_computation
import modules.activities.contributor_registry as activities_contributor_registry
import modules.activities.contributors as activities_contributors

logger = core_logger.get_logger(__name__)

#: How far a stored start may be from the parsed one and still be the same session: activities imported before
#: sub-second times were kept stored whole seconds.
START_TOLERANCE = timedelta(seconds=1)


#: Writes the new values of one stored activity and says whether it was there to take them.
Apply = Callable[["Work", Session], bool]


@dataclass(frozen=True)
class Work:
    """One stored activity, its freshly parsed counterpart and the contributors that store its components.

    Attributes:
        activity_id: The stored activity.
        parsed: What the file yields for it.
        components: The contributor and data of each parsed component that has data.
        expected_file_id: The retained file row the stored activity referenced when its file was read, ``None`` for one
            with no file row; a reprocess writes only while the activity still references it.
    """

    activity_id: uuid.UUID
    parsed: activity_contracts.ParsedActivity
    components: tuple[tuple[activities_contributors.ActivityIngestionContributor, object], ...]
    expected_file_id: uuid.UUID | None = None


def start_of(activity: activity_schema.ActivityRead) -> datetime:
    """Return an activity's start as an aware UTC instant.

    Args:
        activity: The stored activity.

    Returns:
        Its start time.
    """
    start = core_timezone.to_utc_aware(activity.start_time)
    if start is None:
        raise core_exceptions.ProcessingError("The activity has no start time")
    return start


def take_session(
    start_time: datetime, candidates: list[activity_contracts.ParsedActivity]
) -> activity_contracts.ParsedActivity | None:
    """Remove and return the candidate that starts where a stored activity does.

    Args:
        start_time: The stored activity's start.
        candidates: The parsed activities not yet matched.

    Returns:
        The closest candidate within the tolerance, or ``None`` when none starts there.
    """
    closest = min(candidates, key=lambda candidate: abs(candidate.activity.start_time - start_time), default=None)
    if closest is None or abs(closest.activity.start_time - start_time) > START_TOLERANCE:
        return None
    candidates.remove(closest)
    return closest


def components_of(
    parsed: activity_contracts.ParsedActivity,
) -> tuple[tuple[activities_contributors.ActivityIngestionContributor, object], ...]:
    """Resolve the contributor of every component of a parsed activity before anything is written.

    Args:
        parsed: The parsed activity.

    Returns:
        The contributor and data of each component that has data.

    Raises:
        ProcessingError: When a component has no registered contributor, so parsed data is never dropped silently.
    """
    components = []
    for key, data in parsed.components.items():
        if data is None:
            continue
        contributor = activities_contributor_registry.get_activity_ingestion_contributor(key)
        if contributor is None:
            raise core_exceptions.ProcessingError(f"No contributor stores the {key} component")
        components.append((contributor, data))
    return tuple(components)


def plan(
    pairs: Sequence[tuple[uuid.UUID, activity_contracts.ParsedActivity]],
    parsed_file: activity_contracts.ParsedFile,
    expected_file_ids: Mapping[uuid.UUID, uuid.UUID | None] | None = None,
) -> tuple[list[Work], list[tuple[activities_contributors.FileIngestionContributor, object]]]:
    """Resolve the contributor of every component before anything is written.

    Args:
        pairs: The stored activities and their parsed counterparts.
        parsed_file: What the file yields.
        expected_file_ids: The file row each stored activity referenced when read; an activity absent has none.

    Returns:
        The work per activity and the file-scoped contributors with their data.

    Raises:
        ProcessingError: When a component has no registered contributor, so parsed data is never dropped silently.
    """
    expected = expected_file_ids or {}
    work = [
        Work(activity_id, parsed, components_of(parsed), expected.get(activity_id)) for activity_id, parsed in pairs
    ]
    file_work = []
    for key, data in parsed_file.components.items():
        if data is None:
            continue
        file_contributor = activities_contributor_registry.get_file_ingestion_contributor(key)
        if file_contributor is None:
            raise core_exceptions.ProcessingError(f"No contributor stores the {key} file component")
        file_work.append((file_contributor, data))
    return work, file_work


def stage(
    work: Sequence[Work],
    file_work: Sequence[tuple[activities_contributors.FileIngestionContributor, object]],
    apply: Apply,
    db: Session,
) -> bool:
    """Stage the reprocessed activities in the caller's transaction.

    Each activity takes the values ``apply`` writes and has its components replaced. The thumbnail key of an activity
    whose route changed is cleared, a multisport activity's route being its legs' joined, so a render of the old
    track is never served for the new one.

    Args:
        work: The stored activities and what the file yields for each.
        file_work: The file-scoped contributors with their data.
        apply: Writes one activity's new values, and says whether the activity was there to take them.
        db: Database session; the caller commits.

    Returns:
        ``True`` when staged, ``False`` when an activity no longer exists.
    """
    activity_ids = [item.activity_id for item in work]
    routes_before = activity_streams_integration.get_routes_for_reprocess(activity_ids, db)
    for item in work:
        activity = activity_integration.get_activity(item.activity_id, db)
        if activity is None or not apply(item, db):
            return False
        for contributor in activities_contributor_registry.activity_ingestion_contributors():
            contributor.clear(item.activity_id, db)
        for contributor, data in item.components:
            contributor.persist(data, activity, db)
    for file_contributor, data in file_work:
        file_contributor.persist(data, db)
    routes_after = activity_streams_integration.get_routes_for_reprocess(activity_ids, db)
    for activity_id in activity_ids:
        if routes_before.get(activity_id) == routes_after.get(activity_id):
            continue
        stored_key = activity_integration.get_thumbnail_key(activity_id, db)
        if stored_key is not None:
            activity_integration.set_thumbnail_key(activity_id, None, db, expected_key=stored_key)
            logger.debug(
                "Cleared the thumbnail of an activity whose route changed",
                extra=core_logger.context(activity_id=activity_id),
            )
    return True


def write(
    work: Sequence[Work],
    file_work: Sequence[tuple[activities_contributors.FileIngestionContributor, object]],
    apply: Apply,
) -> bool:
    """Write the reprocessed activities in one transaction.

    Args:
        work: The stored activities and what the file yields for each.
        file_work: The file-scoped contributors with their data.
        apply: Writes one activity's new values.

    Returns:
        ``True`` when committed, ``False`` when an activity no longer exists, or no longer references the file its
        values were computed from, and nothing was written.
    """
    with core_database.SessionLocal() as db:
        if not stage(work, file_work, apply, db):
            db.rollback()
            return False
        db.commit()
    logger.debug(
        "Committed a reprocessed activity", extra=core_logger.context(activity_id=work[0].activity_id, count=len(work))
    )
    return True


def _recompute_pairs(
    activity_id: uuid.UUID,
    parsed: activity_contracts.ParsedActivity,
    parsed_file: activity_contracts.ParsedFile,
    db: Session,
) -> list[tuple[uuid.UUID, activity_contracts.ParsedActivity]] | None:
    """Pair the stored activity, and for a multisport one its legs, with what the better source holds for them.

    Args:
        activity_id: The stored activity.
        parsed: Its counterpart in the file: the session, or for a multisport activity the file's parent.
        parsed_file: The file.
        db: Database session.

    Returns:
        The pairs, or ``None`` for a multisport activity whose legs are not the file's sessions, which is attached to
        and not recomputed.
    """
    leg_ids = activity_integration.get_leg_ids_by_parent([activity_id], db).get(activity_id, [])
    if not leg_ids:
        return [(activity_id, parsed)]
    sessions = list(parsed_file.activities)
    pairs = [(activity_id, parsed)]
    for leg_id in leg_ids:
        leg = activity_integration.get_activity(leg_id, db)
        session = take_session(start_of(leg), sessions) if leg is not None else None
        if session is None:
            return None
        pairs.append((leg_id, session))
    return pairs if not sessions else None


def stage_recompute(
    activity_id: uuid.UUID,
    parsed: activity_contracts.ParsedActivity,
    parsed_file: activity_contracts.ParsedFile,
    source: activity_contracts.NewSource,
    expected_file_id: uuid.UUID | None,
    new_file_id: uuid.UUID | None,
    db: Session,
) -> bool:
    """Stage the recompute of an activity from a better source of the same effort, on the caller's session.

    Under the owner's matching lock, in the transaction that matched. The activity is locked and must still reference
    the file row the match saw and hold no source as good as this one; otherwise nothing is staged and the caller
    attaches the source instead. Then:

    - the activity references the new file row, which is marked attached;
    - every derived column and the start take the source's values, an empty one included;
    - the components are cleared and stored again, and a thumbnail whose route changed is cleared;
    - an activity whose only sources are Strava's also takes the source's name and description, and its ``version``
      moves, so a client mid-edit is refused; otherwise ``version`` stays;
    - the source is added.

    Everything the owner, a provider or geocoding owns stays.

    Args:
        activity_id: The activity to recompute.
        parsed: Its counterpart in the file: the session, or for a multisport activity the file's parent.
        parsed_file: The file.
        source: The better source, as the recording identifies.
        expected_file_id: The file row the activity referenced when matched.
        new_file_id: The file row the better source's file was retained as, or ``None`` when it retains none.
        db: Database session; the caller commits, then releases the replaced file.

    Returns:
        ``True`` when staged, ``False`` when the activity changed since it was matched or its structure differs.

    Raises:
        ProcessingError: When a component has no contributor, or an activity vanished.
    """
    user_id = parsed.activity.user_id
    if user_id is None or not activity_integration.lock_for_recompute(
        activity_id, expected_file_id, source.precedence, db
    ):
        return False
    pairs = _recompute_pairs(activity_id, parsed, parsed_file, db)
    if pairs is None:
        return False
    work, _file_work = plan(pairs, parsed_file)
    if new_file_id is not None:
        if not activity_integration.replace_file_id(activity_id, expected_file_id, new_file_id, db):
            return False
        activity_file_storage_integration.mark_attached(new_file_id, db)
    # Read before the source is added: the question is what the activity was.
    take_text = activity_integration.is_live_strava_activity(activity_id, db)

    def apply(item: Work, session: Session) -> bool:
        return activity_integration.apply_recomputed_analysis(
            item.activity_id,
            item.parsed.activity,
            activities_computation.ANALYSIS_VERSION,
            take_text=take_text and item.activity_id == activity_id,
            db=session,
        )

    if not stage(work, [], apply, db):
        raise core_exceptions.ProcessingError("Error recomputing an activity")
    activity_integration.attach_source(activity_id, user_id, source, db)
    logger.debug(
        "Staged the recompute of an activity from a better source",
        extra=core_logger.context(activity_id=activity_id, user_id=user_id, text_taken=take_text),
    )
    return True
