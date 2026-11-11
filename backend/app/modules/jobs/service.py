"""Find a background job by id and list a user's jobs, whichever feature owns them.

A job lives in one of two places. Activity ingestion jobs are database rows. Every other job is a record in the
platform state store, found through :class:`core.attempt_state.JobIndex`; its reference names the kind, and the
kind names the feature that reads it. A caller reads only the jobs they started, with the scope the kind asks for;
an account deletion is also visible to every holder of ``users:read-all``, since any administrator may follow it.
"""

from collections.abc import Callable, Collection
from dataclasses import dataclass
from datetime import datetime

from jasil.providers import StateProvider
from sqlalchemy.orm import Session

import core.attempt_state as core_attempt_state
import core.exceptions as core_exceptions
import core.job_status as core_job_status
import core.logger as core_logger
import core.pagination as core_pagination
import modules.activities.activity.bulk_edit_constants as bulk_edit_constants
import modules.activities.activity.integration_service as activity_integration
import modules.activities.activity_ingestion.constants as activity_ingestion_constants
import modules.activities.activity_ingestion.integration_service as activity_ingestion_integration
import modules.garmin.constants as garmin_constants
import modules.garmin.integration_service as garmin_integration
import modules.jobs.schema as jobs_schema
import modules.strava.constants as strava_constants
import modules.strava.integration_service as strava_integration
import modules.users.users.constants as users_constants
import modules.users.users.integration_service as users_integration
import modules.users.users_profile.constants as profile_constants
import modules.users.users_profile.integration_service as users_profile_integration

logger = core_logger.get_logger(__name__)

_Kind = jobs_schema.JobKind


@dataclass(frozen=True)
class _KindRule:
    """How a kind of job is read.

    Attributes:
        scope: The scope a caller needs to read the job.
        poll_seconds: How long to wait before polling a running job again.
        read: Reads a state-store job from its reference; None for ingestion jobs, which are database rows.
        shared_scope: A scope whose holders may read the job whoever started it.
    """

    scope: str
    poll_seconds: int
    read: Callable[[core_job_status.JobRef, StateProvider], jobs_schema.JobRead | None] | None = None
    shared_scope: str | None = None


_INGESTION_POLL = activity_ingestion_constants.JOB_POLL_SECONDS
_INGESTION_KINDS = activity_ingestion_constants.IngestionJobKind

_RULES: dict[_Kind, _KindRule] = {
    _Kind.ACTIVITY_UPLOAD: _KindRule("activities:upload", _INGESTION_POLL[_INGESTION_KINDS.UPLOAD]),
    _Kind.ACTIVITY_REFRESH: _KindRule("activities:upload", _INGESTION_POLL[_INGESTION_KINDS.REFRESH]),
    _Kind.ACTIVITY_BULK_IMPORT: _KindRule("activities:upload", _INGESTION_POLL[_INGESTION_KINDS.BULK_IMPORT]),
    _Kind.ACTIVITIES_BULK_EDIT: _KindRule(
        "activities:read", bulk_edit_constants.BULK_EDIT_POLL_SECONDS, activity_integration.read_bulk_edit_job
    ),
    _Kind.GARMIN_LINK: _KindRule(
        "account:integrations", garmin_constants.LINK_POLL_SECONDS, garmin_integration.read_link_job
    ),
    _Kind.GARMIN_SYNC_GEAR: _KindRule("account", garmin_constants.SYNC_POLL_SECONDS, garmin_integration.read_sync_job),
    _Kind.GARMIN_SYNC_HEALTH: _KindRule(
        "account", garmin_constants.SYNC_POLL_SECONDS, garmin_integration.read_sync_job
    ),
    _Kind.STRAVA_LINK: _KindRule(
        "account:integrations",
        strava_constants.SYNC_POLL_SECONDS[strava_constants.SyncKind.LINK],
        strava_integration.read_sync_job,
    ),
    _Kind.STRAVA_GEAR: _KindRule(
        "account", strava_constants.SYNC_POLL_SECONDS[strava_constants.SyncKind.GEAR], strava_integration.read_sync_job
    ),
    _Kind.STRAVA_UNLINK: _KindRule(
        "account:integrations",
        strava_constants.SYNC_POLL_SECONDS[strava_constants.SyncKind.UNLINK],
        strava_integration.read_sync_job,
    ),
    _Kind.USER_DELETION: _KindRule(
        "users:read-all",
        users_constants.DELETION_POLL_SECONDS,
        users_integration.read_deletion_job,
        shared_scope="users:read-all",
    ),
    _Kind.PROFILE_EXPORT: _KindRule(
        "account:export", profile_constants.EXPORT_POLL_SECONDS, users_profile_integration.read_export_job
    ),
    _Kind.PROFILE_IMPORT: _KindRule(
        "account:export", profile_constants.IMPORT_POLL_SECONDS, users_profile_integration.read_import_job
    ),
}

_INGESTION = frozenset(kind for kind, rule in _RULES.items() if rule.read is None)

_NOT_FOUND = "Job not found"


@dataclass(frozen=True)
class JobView:
    """A job the caller may see, with what reading it requires.

    Attributes:
        job: The job's status.
        scope: The scope the caller needs to read it.
        poll_seconds: How long to wait before polling it again while it runs.
    """

    job: jobs_schema.JobRead
    scope: str
    poll_seconds: int


def _position(job: jobs_schema.JobRead) -> tuple[datetime, str]:
    return job.created_at, job.id


def _rule_of(job: jobs_schema.JobRead) -> _KindRule:
    return _RULES[_Kind(job.kind)]


def _read_indexed(ref: core_job_status.JobRef, state: StateProvider) -> jobs_schema.JobRead | None:
    try:
        kind = _Kind(ref.kind)
    except ValueError:
        logger.warning("An indexed job has a kind no feature reads", extra=core_logger.context(kind=ref.kind))
        return None
    read = _RULES[kind].read
    return read(ref, state) if read is not None else None


def get_job(job_id: str, caller_id: int, scopes: Collection[str], state: StateProvider, db: Session) -> JobView:
    """Read a job the caller may see.

    Args:
        job_id: The job's identifier.
        caller_id: The authenticated user.
        scopes: The caller's scopes, which decide whether a job someone else started is visible.
        state: The platform state provider.
        db: Database session, for ingestion jobs.

    Returns:
        The job, the scope reading it needs and its poll interval.

    Raises:
        NotFoundError: When no such job exists, it has expired, or the caller may not see it.
        StateUnavailableError: When the state store is unavailable.
    """
    ref = core_attempt_state.JobIndex(state).get(job_id)
    job: jobs_schema.JobRead | None
    if ref is None:
        job = activity_ingestion_integration.read_job(job_id, caller_id, db)
    else:
        job = _read_indexed(ref, state)
        if job is not None and ref.owner_id != caller_id:
            shared = _rule_of(job).shared_scope
            if shared is None or shared not in scopes:
                job = None
    if job is None:
        raise core_exceptions.NotFoundError(_NOT_FOUND)
    rule = _rule_of(job)
    return JobView(job, rule.scope, rule.poll_seconds)


def list_jobs(
    caller_id: int,
    scopes: Collection[str],
    state: StateProvider,
    db: Session,
    *,
    kind: jobs_schema.JobKind | None,
    status: core_job_status.JobState | None,
    cursor: str | None,
    num_records: int,
) -> jobs_schema.JobPage:
    """List a keyset slice of the jobs the caller started, newest first.

    Only the kinds the caller holds the scope for are listed. State-store jobs are kept only while their record
    lasts; ingestion jobs until their retention ends.

    Args:
        caller_id: The authenticated user.
        scopes: The caller's scopes.
        state: The platform state provider.
        db: Database session, for ingestion jobs.
        kind: Only jobs of this kind, when given.
        status: Only jobs in this status, when given.
        cursor: Opaque cursor from the previous slice, or None to start.
        num_records: Slice size.

    Returns:
        The slice and the cursor for the next one.

    Raises:
        InvalidInputError: When the cursor is not one this server issued.
        StateUnavailableError: When the state store is unavailable.
    """
    before = core_pagination.decode_text_cursor(cursor) if cursor else None
    kinds = {listed for listed, rule in _RULES.items() if rule.scope in scopes and (kind is None or listed == kind)}
    jobs: list[jobs_schema.JobRead] = []
    for ref in core_attempt_state.JobIndex(state).list_owned(caller_id):
        if ref.kind not in kinds:
            continue
        job = _read_indexed(ref, state)
        if job is not None and (status is None or job.status == status):
            jobs.append(job)
    if before is not None:
        jobs = [job for job in jobs if _position(job) < before]
    ingestion_kinds = kinds & _INGESTION
    if ingestion_kinds:
        jobs.extend(
            activity_ingestion_integration.list_jobs(
                caller_id, db, kinds=ingestion_kinds, status=status, before=before, limit=num_records + 1
            )
        )
    jobs.sort(key=_position, reverse=True)
    page = jobs[:num_records]
    next_cursor = core_pagination.encode_cursor(*_position(page[-1])) if len(jobs) > num_records else None
    return jobs_schema.JobPage(items=page, num_records=num_records, next_cursor=next_cursor)
