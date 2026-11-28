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

import dataclasses
import hashlib
import os
import tempfile
import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import StrEnum

import jasil.providers as platform_providers
from sqlalchemy.orm import Session

import core.database as core_database
import core.exceptions as core_exceptions
import core.logger as core_logger
import core.timezone as core_timezone
import modules.activities.activity.constants as activity_constants
import modules.activities.activity.contracts as activity_contracts
import modules.activities.activity.integration_service as activity_integration
import modules.activities.activity.schema as activity_schema
import modules.activities.activity_file_storage.contracts as activity_file_storage_contracts
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
        is_leg: Whether the activity is a leg of a multisport activity.
        timezone: The parser's fallback timezone: the activity's stored one, which is the owner's at import for a file
            without a zone of its own, so an owner who moved since does not shift the activity's local times; the
            owner's current one only for an activity stored without a zone.
        units: The owner's measurement units.
        file: The retained file row the activity references, ``None`` for an activity whose file has no row.
    """

    user_id: uuid.UUID
    start_time: datetime
    legs: tuple[tuple[uuid.UUID, datetime], ...]
    is_leg: bool
    timezone: str | None
    units: server_settings_schema.Units
    file: activity_file_storage_contracts.ActivityFileRef | None


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
        file_id = activity_integration.get_file_ids([activity_id], db).get(activity_id)
        file = activity_file_storage_integration.resolve_refs([file_id], db).get(file_id) if file_id else None
        return _Target(
            user_id=activity.user_id,
            start_time=_start_of(activity),
            legs=tuple(legs),
            is_leg=activity.parent_activity_id is not None,
            timezone=activity.timezone or owner.timezone,
            units=server_settings_schema.Units(owner.units),
            file=file,
        )


def _parse(target: _Target, extension: str, data: bytes) -> activity_contracts.ParsedFile | None:
    """Parse a retained file as an upload by its owner would have been.

    Args:
        target: The stored activity.
        extension: The retained file's extension, which names its format.
        data: The retained file's bytes.

    Returns:
        The parsed file.

    Raises:
        DomainError: When the file cannot be parsed.
    """
    with tempfile.TemporaryDirectory(prefix="activity-reprocess-") as work_dir:
        path = os.path.join(work_dir, f"activity{extension}")
        with open(path, "wb") as file:
            file.write(data)
        return activity_ingestion_pipeline_service.parse_file(
            target.user_id, extension, path, None, target.timezone, target.units
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


def _components_of(
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
    work = [_Work(activity_id, parsed, _components_of(parsed)) for activity_id, parsed in pairs]
    file_work = []
    for key, data in parsed_file.components.items():
        if data is None:
            continue
        file_contributor = activities_contributor_registry.get_file_ingestion_contributor(key)
        if file_contributor is None:
            raise core_exceptions.ProcessingError(f"No contributor stores the {key} file component")
        file_work.append((file_contributor, data))
    return work, file_work


def _stage(
    work: Sequence[_Work],
    file_work: Sequence[tuple[activities_contributors.FileIngestionContributor, object]],
    db: Session,
) -> bool:
    """Stage the reprocessed activities in the caller's transaction.

    Each activity takes the new derived columns and has its components replaced. The thumbnail key of an activity
    whose route changed is cleared, a multisport activity's route being its legs' joined, so a render of the old
    track is never served for the new one.

    Args:
        work: The stored activities and what the file yields for each.
        file_work: The file-scoped contributors with their data.
        db: Database session; the caller commits.

    Returns:
        ``True`` when staged, ``False`` when an activity no longer exists.
    """
    activity_ids = [item.activity_id for item in work]
    routes_before = activity_streams_integration.get_routes_for_reprocess(activity_ids, db)
    for item in work:
        activity = activity_integration.get_activity(item.activity_id, db)
        if activity is None or not activity_integration.apply_reprocessed_analysis(
            item.activity_id, item.parsed.activity, activities_computation.ANALYSIS_VERSION, db
        ):
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


def _write(
    work: Sequence[_Work],
    file_work: Sequence[tuple[activities_contributors.FileIngestionContributor, object]],
) -> bool:
    """Write the reprocessed activities in one transaction.

    Args:
        work: The stored activities and what the file yields for each.
        file_work: The file-scoped contributors with their data.

    Returns:
        ``True`` when committed, ``False`` when an activity no longer exists and nothing was written.
    """
    with core_database.SessionLocal() as db:
        if not _stage(work, file_work, db):
            db.rollback()
            return False
        db.commit()
    logger.debug(
        "Committed a reprocessed activity", extra=core_logger.context(activity_id=work[0].activity_id, count=len(work))
    )
    return True


def _write_regrouped(
    parent_id: uuid.UUID,
    parent: activity_contracts.ParsedActivity,
    work: Sequence[_Work],
    file_work: Sequence[tuple[activities_contributors.FileIngestionContributor, object]],
    file_id: uuid.UUID,
) -> uuid.UUID | None:
    """Write the new parent, its adopted legs and their reprocessed values in one transaction.

    Args:
        parent_id: The ID the parent is stored under.
        parent: The parsed multisport activity, with the hash of its file as its source.
        work: The stored legs and what the file yields for each, in start order.
        file_work: The file-scoped contributors with their data.
        file_id: The retained file row the parent references, attached in the same transaction.

    Returns:
        The new parent's ID when committed, ``None`` when nothing was written because a leg is gone or no longer
        standalone, or the parent's key is already stored.
    """
    parent_components = _components_of(parent)
    with core_database.SessionLocal() as db:
        staged = activity_integration.regroup_legs(
            parent, [item.activity_id for item in work], db, activity_id=parent_id, file_id=file_id
        )
        if staged is None:
            db.rollback()
            return None
        activity_file_storage_integration.mark_attached(file_id, db)
        for contributor, data in parent_components:
            contributor.persist(data, staged, db)
        if not _stage(work, file_work, db):
            db.rollback()
            return None
        db.commit()
    logger.debug(
        "Committed a regrouped multisport activity",
        extra=core_logger.context(activity_id=staged.id, count=len(work)),
    )
    return staged.id


def _find_siblings(
    target: _Target,
    parsed_file: activity_contracts.ParsedFile,
    content_hash: str,
    storage: platform_providers.StorageProvider,
) -> list[uuid.UUID] | None:
    """Find the stored activity each parsed leg was stored as.

    A sibling belongs to the same user, has no parent and no legs, starts within the tolerance of its leg and
    retains a file with the same SHA-256 as the one being reprocessed. A file with a row is compared by the row's
    SHA-256; one without is read and hashed, with no session open.

    Args:
        target: The activity being reprocessed.
        parsed_file: What its file yields.
        content_hash: The SHA-256 of the file.
        storage: The blob-storage provider the files are retained in.

    Returns:
        The sibling of each leg of the file, in the legs' order, or ``None`` when any leg has none.
    """
    with core_database.SessionLocal() as db:
        candidates = {
            candidate.id: _start_of(candidate)
            for leg in parsed_file.activities
            for candidate in activity_integration.list_standalone_activities_starting_between(
                target.user_id,
                leg.activity.start_time - _START_TOLERANCE,
                leg.activity.start_time + _START_TOLERANCE,
                db,
            )
        }
        file_ids = activity_integration.get_file_ids(list(candidates), db)
        refs = activity_file_storage_integration.resolve_refs(list(file_ids.values()), db)
    same_file = {}
    for candidate_id, start in candidates.items():
        ref = refs.get(file_ids[candidate_id]) if candidate_id in file_ids else None
        if ref is not None:
            matches = ref.sha256 == content_hash
        else:
            stored_file = activity_file_storage_integration.read_file(candidate_id, None, storage)
            matches = stored_file is not None and hashlib.sha256(stored_file[1]).hexdigest() == content_hash
        if matches:
            same_file[candidate_id] = start
    siblings = []
    for leg in parsed_file.activities:
        closest = min(
            same_file,
            key=lambda candidate_id: abs(same_file[candidate_id] - leg.activity.start_time),
            default=None,
        )
        if closest is None or abs(same_file[closest] - leg.activity.start_time) > _START_TOLERANCE:
            return None
        siblings.append(closest)
        del same_file[closest]
    return siblings


def _regroup(
    activity_id: uuid.UUID,
    target: _Target,
    parsed_file: activity_contracts.ParsedFile,
    parent: activity_contracts.ParsedActivity,
    extension: str,
    data: bytes,
    storage: platform_providers.StorageProvider,
) -> ReprocessOutcome | None:
    """Regroup the legs a multi-session file was stored as under a new multisport activity, and reprocess them.

    The file is staged as a retained file row first, with no session open, so the parent never exists without it, and
    attached in the transaction that writes the group. If that stages nothing or raises, a row this call created is
    removed again. Only after the commit are the legs' copies, which the legs hold under their own IDs while their
    file has no row, deleted. A crash after staging leaves a ``pending`` row the daily sweep removes; a crash after
    the commit leaves spare leg copies, which the sweep of the ``processed`` files removes.

    Args:
        activity_id: The activity being reprocessed, one of the legs.
        target: What is known of it.
        parsed_file: What its file yields.
        parent: The file's multisport activity.
        extension: The retained file's extension.
        data: The retained file's bytes.
        storage: The blob-storage provider the files are retained in.

    Returns:
        What was done, or ``None`` when the legs cannot be regrouped and the activity is to be reprocessed alone.

    Raises:
        DomainError: When a component has no registered contributor.
    """
    content_hash = hashlib.sha256(data).hexdigest()
    siblings = _find_siblings(target, parsed_file, content_hash, storage)
    if siblings is None or activity_id not in siblings:
        logger.warning(
            "Not regrouping a legacy multisport leg: a leg of its file has no stored sibling with the same file",
            extra=core_logger.context(activity_id=activity_id, user_id=target.user_id),
        )
        return None
    work, file_work = _plan(list(zip(siblings, parsed_file.activities, strict=True)), parsed_file)
    source = activity_contracts.ImportSource(
        kind="reprocess", content_hash=content_hash, precedence=activity_constants.file_source_precedence(extension)
    )
    parent_id = uuid.uuid4()
    staged_file = activity_file_storage_integration.stage_file(target.user_id, content_hash, extension, data, storage)
    try:
        written = _write_regrouped(
            parent_id, dataclasses.replace(parent, source=source), work, file_work, staged_file.ref.file_id
        )
    except BaseException:
        if staged_file.created:
            activity_file_storage_integration.release_unattached(staged_file.ref.file_id, storage)
        raise
    if written is None:
        if staged_file.created:
            activity_file_storage_integration.release_unattached(staged_file.ref.file_id, storage)
        logger.warning(
            "Not regrouping a legacy multisport leg: the group changed or its key is taken",
            extra=core_logger.context(activity_id=activity_id, user_id=target.user_id),
        )
        return None
    for sibling in siblings:
        activity_file_storage_integration.delete_legacy_activity_file(sibling, storage)
    logger.info(
        "Regrouped legacy multisport legs under a new parent",
        extra=core_logger.context(activity_id=parent_id, user_id=target.user_id, count=len(siblings)),
    )
    return ReprocessOutcome.REPROCESSED


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
        activity_file_storage_integration.read_file(activity_id, target.file, storage) if target is not None else None
    )
    if target is None or stored_file is None:
        logger.debug(
            "Nothing to reprocess: no activity or no retained file", extra=core_logger.context(activity_id=activity_id)
        )
        return ReprocessOutcome.NO_FILE
    extension, data = stored_file

    try:
        parsed_file = _parse(target, extension, data)
        if parsed_file is not None and parsed_file.parent is not None and not target.legs and not target.is_leg:
            regrouped = _regroup(activity_id, target, parsed_file, parsed_file.parent, extension, data, storage)
            if regrouped is not None:
                return regrouped
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
