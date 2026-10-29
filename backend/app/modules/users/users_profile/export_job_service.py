"""Run a profile export off the request: accept it, build it on a worker, and offer the result.

The request answers 202 and a worker builds the archive into storage, so no API thread is held
for the build. With durable jobs (``JOBS_ENABLED``) a jasil worker runs it and retries a transient
failure; without them the same body runs on the in-process subscriber pool. Either way the state in
the shared state store is what the client polls, and its claim stops a user queueing two exports.

An export only reads, and each run replaces the user's one staged archive, so running it again after
a worker died is safe.
"""

import time
from collections.abc import Generator

import jasil.providers as platform_providers
from sqlalchemy.orm import Session

import core.config as core_config
import core.database as core_database
import core.exceptions as core_exceptions
import core.logger as core_logger
import modules.users.users_profile.constants as profile_constants
import modules.users.users_profile.event_publishers as profile_event_publishers
import modules.users.users_profile.events as profile_events
import modules.users.users_profile.exceptions as profile_exceptions
import modules.users.users_profile.export_state_store as profile_export_state_store
import modules.users.users_profile.service as profile_service
import modules.users.users_profile.transfer_pool as profile_transfer_pool

logger = core_logger.get_logger(__name__)

_Status = profile_constants.ExportStatus
_Failure = profile_constants.ExportFailure

_STREAM_CHUNK_BYTES = 64 * 1024


def request_export(
    user_id: int,
    states: profile_export_state_store.ProfileExportStateStore,
    db: Session,
) -> profile_export_state_store.ProfileExportState:
    """Queue an export of the user's profile.

    Args:
        user_id: The exporting user.
        states: Shared store of the export's state.
        db: Database session.

    Returns:
        The export's initial state.

    Raises:
        ConflictError: When the user already has an export pending.
        ServiceUnavailableError: When there is no durable worker and the in-process pool is full.
    """
    if not core_config.settings.JOBS_ENABLED:
        profile_transfer_pool.pool.require_capacity()
    if not states.begin(user_id):
        logger.debug("Refused a second profile export while one is pending", extra=core_logger.context(user_id=user_id))
        raise core_exceptions.ConflictError("A profile export is already in progress")

    try:
        profile_event_publishers.publish_export_requested(user_id, db, commit=db.commit)
    except BaseException:
        # The export never started, so nothing else would finish its claim.
        states.set_status(user_id, _Status.FAILED, failure=_Failure.PROCESSING_FAILED)
        raise

    logger.info("Profile export queued", extra=core_logger.context(user_id=user_id))
    return profile_export_state_store.ProfileExportState(status=_Status.QUEUED)


def fail_unstarted_export(
    payload: profile_events.ProfileExportRequestedPayload,
    states: profile_export_state_store.ProfileExportStateStore,
) -> None:
    """Close an export that no worker took, so the user can request another.

    Args:
        payload: Whose profile was to be exported.
        states: Shared store of the export's state.
    """
    logger.warning(
        "Closed a profile export the in-process pool could not take", extra=core_logger.context(user_id=payload.user_id)
    )
    states.set_status(payload.user_id, _Status.FAILED, failure=_Failure.PROCESSING_FAILED)


def close_dead_lettered_export(
    payload: profile_events.ProfileExportRequestedPayload,
    states: profile_export_state_store.ProfileExportStateStore,
) -> None:
    """Close an export the runner gave up on, so the user can request another.

    Runs however the last attempt ended, including a lease that expired or a worker that died, where
    :func:`run_export` never got to record it. An export that already finished, or whose state has
    expired, is left as it is.

    Args:
        payload: Whose profile was to be exported.
        states: Shared store of the export's state.
    """
    state = states.get(payload.user_id)
    if state is None or state.status not in (_Status.QUEUED, _Status.RUNNING):
        return
    states.set_status(payload.user_id, _Status.FAILED, failure=_Failure.PROCESSING_FAILED)
    logger.error("A profile export was dead-lettered", extra=core_logger.context(user_id=payload.user_id))


def get_export_status(
    user_id: int, states: profile_export_state_store.ProfileExportStateStore
) -> profile_export_state_store.ProfileExportState:
    """Report where the user's profile export is.

    Args:
        user_id: The exporting user.
        states: Shared store of the export's state.

    Returns:
        The export's state.

    Raises:
        NotFoundError: When no export is recorded or it has expired.
    """
    state = states.get(user_id)
    if state is None:
        raise core_exceptions.NotFoundError("No profile export recorded")

    return state


def open_export(
    user_id: int,
    states: profile_export_state_store.ProfileExportStateStore,
    storage: platform_providers.StorageProvider,
) -> tuple[Generator[bytes], int]:
    """Open the user's finished export for download.

    Args:
        user_id: The exporting user.
        states: Shared store of the export's state.
        storage: The platform storage provider.

    Returns:
        The archive, read from storage chunk by chunk, and its size in bytes.

    Raises:
        NotFoundError: When no finished export is available, or its archive is gone.
    """
    state = states.get(user_id)
    if state is None or state.status != _Status.COMPLETED or state.size_bytes is None:
        raise core_exceptions.NotFoundError("No finished profile export to download")

    try:
        source = storage.open_stream(
            profile_constants.EXPORT_STAGING_AREA, profile_constants.export_staged_key(user_id)
        )
    except FileNotFoundError as err:
        logger.warning("The staged profile export is missing", extra=core_logger.context(user_id=user_id))
        raise core_exceptions.NotFoundError("No finished profile export to download") from err

    def chunks() -> Generator[bytes]:
        with source:
            while chunk := source.read(_STREAM_CHUNK_BYTES):
                yield chunk

    return chunks(), state.size_bytes


def run_export(
    payload: profile_events.ProfileExportRequestedPayload,
    states: profile_export_state_store.ProfileExportStateStore,
    storage: platform_providers.StorageProvider,
    *,
    will_retry: bool,
) -> None:
    """Build and stage one export and record the outcome. Blocking; call it from a worker.

    Args:
        payload: Whose profile to export.
        states: Shared store of the export's state.
        storage: The platform storage provider.
        will_retry: Whether a worker will run this again if it raises.

    Raises:
        Exception: A transient failure, when ``will_retry``, so the worker runs the export again;
            the state goes back to ``QUEUED`` first.
    """
    user_id = payload.user_id
    state = states.get(user_id)
    if state is None or state.status not in (_Status.QUEUED, _Status.RUNNING):
        logger.debug("Skipped a profile export that is not pending", extra=core_logger.context(user_id=user_id))
        return

    states.set_status(user_id, _Status.RUNNING)
    try:
        with core_database.SessionLocal() as db:
            size = profile_service.stage_export(user_id, storage, db)
    except Exception as err:
        if will_retry and profile_exceptions.is_transient(err):
            logger.warning(
                "Profile export failed; it will be retried", exc_info=err, extra=core_logger.context(user_id=user_id)
            )
            states.set_status(user_id, _Status.QUEUED)
            raise
        timed_out = isinstance(err, profile_exceptions.TransferTimeoutError)
        failure = _Failure.TIMED_OUT if timed_out else _Failure.PROCESSING_FAILED
        logger.error("Profile export failed", exc_info=err, extra=core_logger.context(user_id=user_id, failure=failure))
        states.set_status(user_id, _Status.FAILED, failure=failure)
        return

    states.set_status(user_id, _Status.COMPLETED, size_bytes=size)
    logger.info("Profile data export ready", extra=core_logger.context(user_id=user_id, size_bytes=size))


def sweep_staged_exports(storage: platform_providers.StorageProvider, older_than_seconds: float) -> int:
    """Delete staged exports that are past their download window.

    The net for a user who never downloaded theirs, and for a worker that died mid-stage.

    Args:
        storage: The platform storage provider.
        older_than_seconds: A staged export older than this is removed.

    Returns:
        How many archives were removed.
    """
    cutoff = time.time() - older_than_seconds
    stale = [key for key, modified in storage.iter_objects(profile_constants.EXPORT_STAGING_AREA) if modified < cutoff]
    removed = 0
    for key in stale:
        try:
            storage.delete(profile_constants.EXPORT_STAGING_AREA, key)
        except Exception as err:
            logger.warning("Could not delete a stale staged profile export", exc_info=err)
        else:
            removed += 1
    if removed:
        logger.info("Removed stale staged profile exports", extra=core_logger.context(removed=removed))
    return removed


def discard_staged_export(user_id: int, storage: platform_providers.StorageProvider) -> None:
    """Delete a user's staged export, leaving the sweep to catch it if storage fails.

    Args:
        user_id: The user whose export to remove.
        storage: The platform storage provider.
    """
    try:
        storage.delete(profile_constants.EXPORT_STAGING_AREA, profile_constants.export_staged_key(user_id))
    except Exception as err:
        logger.warning(
            "Could not delete a user's staged profile export", exc_info=err, extra=core_logger.context(user_id=user_id)
        )
