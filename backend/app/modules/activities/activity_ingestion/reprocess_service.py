"""Reprocess one stored activity in place from its retained source file.

A reprocess runs the file through today's parsers and analysis again and writes the result over what an older
analysis stored: the parser-derived columns, the streams, laps, sets and workout steps, and the file's exercise
titles. It never creates an activity and never touches what the owner, a provider or geocoding owns, so the activity
keeps its id, ``version`` (an open edit's ``ETag`` stays valid), media, comments and public links.

It publishes no event, as :func:`~modules.activities.activity.integration_service.restore_activity` does not: the
activity is not new, so ``activity.created`` would notify the owner again, and the one derived artifact a change can
invalidate, the map thumbnail, is cleared and left for the thumbnail backfill to render again.

No database session is open while the file is read or parsed. A short session reads what the parse needs, then one
transaction writes the activity (a multisport activity with its legs, as they were stored together) and commits.
"""

import os
import tempfile
import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import StrEnum

import jasil.providers as platform_providers

import core.database as core_database
import core.exceptions as core_exceptions
import core.logger as core_logger
import core.timezone as core_timezone
import modules.activities.activity.contracts as activity_contracts
import modules.activities.activity.integration_service as activity_integration
import modules.activities.activity.schema as activity_schema
import modules.activities.activity_file_storage.integration_service as activity_file_storage_integration
import modules.activities.activity_ingestion.pipeline_service as activity_ingestion_pipeline_service
import modules.activities.activity_streams.integration_service as activity_streams_integration
import modules.activities.computation as activities_computation
import modules.activities.contributor_registry as activities_contributor_registry
import modules.activities.contributors as activities_contributors
import modules.server_settings.schema as server_settings_schema
import modules.users.users.integration_service as users_integration

logger = core_logger.get_logger(__name__)

#: How far a stored start may be from the parsed one and still be the same session: activities imported before
#: sub-second times were kept stored whole seconds.
_START_TOLERANCE = timedelta(seconds=1)


class ReprocessOutcome(StrEnum):
    """What a reprocess did with one activity.

    Attributes:
        REPROCESSED: The activity was recomputed from its file and written.
        NO_FILE: There is no activity to read or it has no retained file (a Strava API import, a manual entry, a leg
            of a multisport activity, whose file is kept under its parent).
        NO_SESSION: The file holds no session that starts where the activity does; nothing was written.
        FAILED: The file could not be parsed; nothing was written.
    """

    REPROCESSED = "reprocessed"
    NO_FILE = "no_file"
    NO_SESSION = "no_session"
    FAILED = "failed"


@dataclass(frozen=True)
class _Target:
    """What the parse and the match need to know about the stored activity.

    Attributes:
        user_id: The owner.
        start_time: When the activity starts.
        legs: The ID and start of each leg when the activity is a multisport activity, in start order.
        timezone: The parser's fallback timezone: the activity's stored one, which is the owner's at import for a file
            without a zone of its own, so an owner who moved since does not shift the activity's local times; the
            owner's current one only for an activity stored without a zone.
        units: The owner's measurement units.
    """

    user_id: uuid.UUID
    start_time: datetime
    legs: tuple[tuple[uuid.UUID, datetime], ...]
    timezone: str | None
    units: server_settings_schema.Units


@dataclass(frozen=True)
class _Work:
    """One stored activity, its freshly parsed counterpart and the contributors that store its components.

    Attributes:
        activity_id: The stored activity.
        parsed: What the file yields for it.
        components: The contributor and data of each parsed component that has data.
    """

    activity_id: uuid.UUID
    parsed: activity_contracts.ParsedActivity
    components: tuple[tuple[activities_contributors.ActivityIngestionContributor, object], ...]


def _start_of(activity: activity_schema.ActivityRead) -> datetime:
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


def _read_target(activity_id: uuid.UUID) -> _Target | None:
    """Read what a reprocess needs of an activity and its owner in one short session.

    Args:
        activity_id: The activity.

    Returns:
        The target, or ``None`` when the activity or its owner does not exist.
    """
    with core_database.SessionLocal() as db:
        activity = activity_integration.get_activity(activity_id, db)
        if activity is None or activity.user_id is None:
            return None
        owner = users_integration.get_user(activity.user_id, db)
        if owner is None:
            return None
        legs = []
        for leg_id in activity_integration.get_leg_ids_by_parent([activity_id], db).get(activity_id, []):
            leg = activity_integration.get_activity(leg_id, db)
            if leg is not None:
                legs.append((leg_id, _start_of(leg)))
        return _Target(
            user_id=activity.user_id,
            start_time=_start_of(activity),
            legs=tuple(legs),
            timezone=activity.timezone or owner.timezone,
            units=server_settings_schema.Units(owner.units),
        )


def _parse(target: _Target, key: str, data: bytes) -> activity_contracts.ParsedFile | None:
    """Parse a retained file as an upload by its owner would have been.

    Args:
        target: The stored activity.
        key: The retained file's storage key, whose extension names its format.
        data: The retained file's bytes.

    Returns:
        The parsed file.

    Raises:
        DomainError: When the file cannot be parsed.
    """
    with tempfile.TemporaryDirectory(prefix="activity-reprocess-") as work_dir:
        path = os.path.join(work_dir, f"activity{os.path.splitext(key)[1]}")
        with open(path, "wb") as file:
            file.write(data)
        return activity_ingestion_pipeline_service.parse_file(
            target.user_id, os.path.splitext(key)[1], path, None, target.timezone, target.units
        )


def _take_session(
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
    if closest is None or abs(closest.activity.start_time - start_time) > _START_TOLERANCE:
        return None
    candidates.remove(closest)
    return closest


def _match(
    activity_id: uuid.UUID, target: _Target, parsed_file: activity_contracts.ParsedFile
) -> list[tuple[uuid.UUID, activity_contracts.ParsedActivity]] | None:
    """Pair each stored activity with the parsed one it was stored from.

    A multisport activity takes the file's parent and each of its legs the file's leg that starts where it does. Any
    other activity, a leg stored on its own before groups existed included, takes the session that starts where it
    does.

    Args:
        activity_id: The stored activity.
        target: What is known of it.
        parsed_file: What its file yields.

    Returns:
        The pairs, or ``None`` when any stored activity has no session to match.
    """
    sessions = list(parsed_file.activities)
    if not target.legs:
        session = _take_session(target.start_time, sessions)
        return None if session is None else [(activity_id, session)]
    if parsed_file.parent is None:
        return None
    pairs = [(activity_id, parsed_file.parent)]
    for leg_id, leg_start in target.legs:
        session = _take_session(leg_start, sessions)
        if session is None:
            return None
        pairs.append((leg_id, session))
    return pairs


def _plan(
    pairs: Sequence[tuple[uuid.UUID, activity_contracts.ParsedActivity]],
    parsed_file: activity_contracts.ParsedFile,
) -> tuple[list[_Work], list[tuple[activities_contributors.FileIngestionContributor, object]]]:
    """Resolve the contributor of every component before anything is written.

    Args:
        pairs: The stored activities and their parsed counterparts.
        parsed_file: What the file yields.

    Returns:
        The work per activity and the file-scoped contributors with their data.

    Raises:
        ProcessingError: When a component has no registered contributor, so parsed data is never dropped silently.
    """
    work = []
    for activity_id, parsed in pairs:
        components = []
        for key, data in parsed.components.items():
            if data is None:
                continue
            contributor = activities_contributor_registry.get_activity_ingestion_contributor(key)
            if contributor is None:
                raise core_exceptions.ProcessingError(f"No contributor stores the {key} component")
            components.append((contributor, data))
        work.append(_Work(activity_id, parsed, tuple(components)))
    file_work = []
    for key, data in parsed_file.components.items():
        if data is None:
            continue
        file_contributor = activities_contributor_registry.get_file_ingestion_contributor(key)
        if file_contributor is None:
            raise core_exceptions.ProcessingError(f"No contributor stores the {key} file component")
        file_work.append((file_contributor, data))
    return work, file_work


def _write(
    work: Sequence[_Work],
    file_work: Sequence[tuple[activities_contributors.FileIngestionContributor, object]],
) -> bool:
    """Write the reprocessed activities in one transaction.

    Each activity takes the new derived columns and has its components replaced. The thumbnail key of an activity
    whose route changed is cleared, a multisport activity's route being its legs' joined, so a render of the old
    track is never served for the new one.

    Args:
        work: The stored activities and what the file yields for each.
        file_work: The file-scoped contributors with their data.

    Returns:
        ``True`` when committed, ``False`` when an activity no longer exists and nothing was written.
    """
    activity_ids = [item.activity_id for item in work]
    with core_database.SessionLocal() as db:
        routes_before = activity_streams_integration.get_route_waypoints_for_activities(activity_ids, db)
        for item in work:
            activity = activity_integration.get_activity(item.activity_id, db)
            if activity is None or not activity_integration.apply_reprocessed_analysis(
                item.activity_id, item.parsed.activity, activities_computation.ANALYSIS_VERSION, db
            ):
                db.rollback()
                return False
            for contributor in activities_contributor_registry.activity_ingestion_contributors():
                contributor.clear(item.activity_id, db)
            for contributor, data in item.components:
                contributor.persist(data, activity, db)
        for file_contributor, data in file_work:
            file_contributor.persist(data, db)
        routes_after = activity_streams_integration.get_route_waypoints_for_activities(activity_ids, db)
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
        db.commit()
    logger.debug(
        "Committed a reprocessed activity", extra=core_logger.context(activity_id=activity_ids[0], count=len(work))
    )
    return True


def reprocess_activity(activity_id: uuid.UUID, storage: platform_providers.StorageProvider) -> ReprocessOutcome:
    """Recompute one activity from its retained file and write it over the stored values.

    Args:
        activity_id: The activity to reprocess.
        storage: The blob-storage provider the source file is retained in.

    Returns:
        What was done; for anything but ``REPROCESSED`` nothing was written.
    """
    target = _read_target(activity_id)
    stored_file = (
        activity_file_storage_integration.get_activity_file(activity_id, storage) if target is not None else None
    )
    if target is None or stored_file is None:
        logger.debug(
            "Nothing to reprocess: no activity or no retained file", extra=core_logger.context(activity_id=activity_id)
        )
        return ReprocessOutcome.NO_FILE
    key, data = stored_file

    try:
        parsed_file = _parse(target, key, data)
        pairs = None if parsed_file is None else _match(activity_id, target, parsed_file)
        plan = None if pairs is None or parsed_file is None else _plan(pairs, parsed_file)
    except core_exceptions.DomainError as err:
        logger.warning(
            "Could not reprocess an activity: its retained file was refused",
            exc_info=err,
            extra=core_logger.context(activity_id=activity_id, user_id=target.user_id),
        )
        return ReprocessOutcome.FAILED
    if plan is None:
        logger.warning(
            "Could not reprocess an activity: its file has no session that starts where it does",
            extra=core_logger.context(activity_id=activity_id, user_id=target.user_id),
        )
        return ReprocessOutcome.NO_SESSION

    if not _write(*plan):
        logger.debug(
            "Nothing was reprocessed: an activity was deleted meanwhile",
            extra=core_logger.context(activity_id=activity_id, user_id=target.user_id),
        )
        return ReprocessOutcome.NO_FILE
    return ReprocessOutcome.REPROCESSED
