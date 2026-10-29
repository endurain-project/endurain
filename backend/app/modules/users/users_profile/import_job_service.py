"""Run a profile import off the request: accept it, work it on a worker, and report its state.

The archive is staged in storage, the request answers 202, and a worker imports it. With durable
jobs (``JOBS_ENABLED``) a jasil worker runs it and retries a failure; without them the same body
runs on the in-process subscriber pool. Either way the state in the shared state store is what the
client polls, and its claim stops a user queueing two imports.

The database part of the import is one transaction, so a failure before its commit leaves nothing
behind and can be retried. Once it is committed a retry would import everything twice, so a failure
from then on is final.
"""

import asyncio
import tempfile
import time
from collections.abc import Callable
from typing import Protocol
from uuid import uuid4

import jasil.providers as platform_providers
from pydantic import ValidationError
from sqlalchemy.orm import Session

import core.config as core_config
import core.database as core_database
import core.exceptions as core_exceptions
import core.file_uploads as core_file_uploads
import core.logger as core_logger
import modules.users.users_profile.constants as profile_constants
import modules.users.users_profile.event_publishers as profile_event_publishers
import modules.users.users_profile.events as profile_events
import modules.users.users_profile.exceptions as profile_exceptions
import modules.users.users_profile.import_service as profile_import_service
import modules.users.users_profile.import_state_store as profile_import_state_store
import modules.users.users_profile.transfer_pool as profile_transfer_pool

logger = core_logger.get_logger(__name__)

_Status = profile_constants.ImportStatus
_Failure = profile_constants.ImportFailure

#: Failures that come from the archive the user supplied, with the code each one is reported as.
_REJECTION_CODES: tuple[tuple[type[Exception], profile_constants.ImportFailure], ...] = (
    (profile_exceptions.FileSizeError, _Failure.TOO_LARGE),
    (profile_exceptions.ActivityLimitError, _Failure.TOO_MANY_ACTIVITIES),
    (profile_exceptions.ImportTimeoutError, _Failure.TIMED_OUT),
    (profile_exceptions.ImportValidationError, _Failure.INVALID_FILE),
    (profile_exceptions.FileFormatError, _Failure.INVALID_FILE),
    (profile_exceptions.ZipStructureError, _Failure.INVALID_FILE),
    (profile_exceptions.JSONParseError, _Failure.INVALID_FILE),
    (profile_exceptions.SchemaValidationError, _Failure.INVALID_FILE),
    (core_exceptions.InvalidInputError, _Failure.INVALID_FILE),
    (ValidationError, _Failure.INVALID_FILE),
)


class UploadSaver(Protocol):
    """Callable that validates the request's upload and streams it to local disk."""

    def __call__(self, *, kind: core_file_uploads.UploadKind, upload_dir: str, filename: str) -> str:
        """Validate the upload and save it as ``upload_dir/filename``.

        The router binds the request's file to the shared upload writer, so nothing below the router
        handles the transport's file object.

        Args:
            kind: Logical content type, which drives the validator and size cap.
            upload_dir: Trusted destination directory.
            filename: Server-generated filename within ``upload_dir``.

        Returns:
            Absolute filesystem path of the saved file.
        """
        ...


def request_import(
    user_id: int,
    save_upload: UploadSaver,
    states: profile_import_state_store.ProfileImportStateStore,
    storage: platform_providers.StorageProvider,
    db: Session,
) -> profile_import_state_store.ProfileImportState:
    """Validate an upload, stage it and queue its import.

    The claim and the pool are checked before the body is read, so a request that will be refused never
    pays for receiving up to 500 MB. The archive goes to disk and from there into storage in chunks, so
    it is never held in memory.

    Args:
        user_id: The importing user.
        save_upload: Validates the request's upload and streams it to local disk.
        states: Shared store of the import's state.
        storage: The platform storage provider.
        db: Database session.

    Returns:
        The import's initial state.

    Raises:
        ConflictError: When the user already has an import pending.
        ServiceUnavailableError: When there is no durable worker and the in-process pool is full.
        DomainError: When the shared upload validators reject the archive.
    """
    if not core_config.settings.JOBS_ENABLED:
        profile_transfer_pool.pool.require_capacity()
    if not states.begin(user_id):
        logger.debug("Refused a second profile import while one is pending", extra=core_logger.context(user_id=user_id))
        raise core_exceptions.ConflictError("A profile import is already in progress")

    staged_key = f"{user_id}/{uuid4()}.zip"
    with tempfile.TemporaryDirectory(prefix="profile-import-") as incoming_dir:
        try:
            incoming_path = save_upload(
                kind=core_file_uploads.UploadKind.ZIP, upload_dir=incoming_dir, filename="archive.zip"
            )
        except BaseException:
            # A rejected upload is answered synchronously, so there is no import to report on.
            states.discard(user_id)
            raise
        try:
            with open(incoming_path, "rb") as archive:
                storage.save_stream(profile_constants.IMPORT_STAGING_AREA, staged_key, archive)
            profile_event_publishers.publish_import_requested(user_id, staged_key, db, commit=db.commit)
        except BaseException:
            # The import never started, so nothing else would finish its claim or remove its archive.
            _discard_staged(staged_key, storage)
            states.set_status(user_id, _Status.FAILED, failure=_Failure.PROCESSING_FAILED)
            raise

    logger.info("Profile import queued", extra=core_logger.context(user_id=user_id))
    return profile_import_state_store.ProfileImportState(status=_Status.QUEUED)


def fail_unstarted_import(
    payload: profile_events.ProfileImportRequestedPayload,
    states: profile_import_state_store.ProfileImportStateStore,
    storage: platform_providers.StorageProvider,
) -> None:
    """Close an import that no worker took, so the user can start another.

    Args:
        payload: Which archive was to be imported and for whom.
        states: Shared store of the import's state.
        storage: The platform storage provider.
    """
    logger.warning(
        "Closed a profile import the in-process pool could not take", extra=core_logger.context(user_id=payload.user_id)
    )
    states.set_status(payload.user_id, _Status.FAILED, failure=_Failure.PROCESSING_FAILED)
    _discard_staged(payload.staged_key, storage)


def close_dead_lettered_import(
    payload: profile_events.ProfileImportRequestedPayload,
    states: profile_import_state_store.ProfileImportStateStore,
    storage: platform_providers.StorageProvider,
) -> None:
    """Close an import the runner gave up on, so the user can start another.

    Runs however the last attempt ended, including a lease that expired or a worker that died, where
    :func:`run_import` never got to record it. A pending import fails with the reason its state
    implies: one that died while writing files left some of them behind. An import that already
    finished keeps its outcome, and the staged archive is removed either way.

    Args:
        payload: Which archive was to be imported and for whom.
        states: Shared store of the import's state.
        storage: The platform storage provider.
    """
    state = states.get(payload.user_id)
    if state is not None and state.status in (_Status.QUEUED, _Status.RUNNING, _Status.WRITING_FILES):
        failure = _Failure.FILES_INCOMPLETE if state.status == _Status.WRITING_FILES else _Failure.PROCESSING_FAILED
        states.set_status(payload.user_id, _Status.FAILED, failure=failure)
        logger.error(
            "A profile import was dead-lettered",
            extra=core_logger.context(user_id=payload.user_id, failure=failure),
        )
    _discard_staged(payload.staged_key, storage)


def get_import_status(
    user_id: int, states: profile_import_state_store.ProfileImportStateStore
) -> profile_import_state_store.ProfileImportState:
    """Report where the user's profile import is.

    Args:
        user_id: The importing user.
        states: Shared store of the import's state.

    Returns:
        The import's state.

    Raises:
        NotFoundError: When no import is recorded or it has expired.
    """
    state = states.get(user_id)
    if state is None:
        raise core_exceptions.NotFoundError("No profile import recorded")

    return state


def _discard_staged(staged_key: str, storage: platform_providers.StorageProvider) -> None:
    """Delete a staged archive, leaving the sweep to catch it if storage fails.

    Args:
        staged_key: Storage key of the archive.
        storage: The platform storage provider.
    """
    try:
        storage.delete(profile_constants.IMPORT_STAGING_AREA, staged_key)
    except Exception as err:
        logger.warning("Could not delete a staged profile import", exc_info=err)


def _rejection_code(err: Exception) -> profile_constants.ImportFailure | None:
    """Return the code for a failure caused by the archive itself.

    Args:
        err: What the import raised.

    Returns:
        The code, or None when the failure is not the archive's doing.
    """
    for error_type, code in _REJECTION_CODES:
        if isinstance(err, error_type):
            return code
    return None


def _run_importer(
    user_id: int,
    zip_data: bytes,
    storage: platform_providers.StorageProvider,
    on_committed: Callable[[], None],
) -> dict[str, int]:
    """Import an archive on a session of its own.

    Args:
        user_id: The importing user.
        zip_data: The archive.
        storage: The platform storage provider.
        on_committed: Called once the database rows are committed, before the files are written.

    Returns:
        How many items of each kind were imported.
    """
    with core_database.SessionLocal() as db:
        importer = profile_import_service.ImportService(
            user_id,
            storage,
            db,
            on_database_committed=on_committed,
        )
        # The importer awaits file validation, so it needs a loop; this runs on a worker thread
        # with none, and the importer shares no loop-bound resources.
        return asyncio.run(importer.import_from_zip_data(zip_data))["imported"]


def run_import(
    payload: profile_events.ProfileImportRequestedPayload,
    states: profile_import_state_store.ProfileImportStateStore,
    storage: platform_providers.StorageProvider,
    *,
    will_retry: bool,
) -> None:
    """Import one staged archive and record the outcome. Blocking; call it from a worker.

    A redelivery after a worker died is safe while the import was in its database part, because
    that part rolled back with the worker. If it had reached the files, the rows are already in
    and importing again would duplicate them, so that import is closed as incomplete instead.

    Args:
        payload: Which archive to import and for whom.
        states: Shared store of the import's state.
        storage: The platform storage provider.
        will_retry: Whether a worker will run this again if it raises.

    Raises:
        Exception: A transient failure before the database commit, when ``will_retry``, so the
            worker runs the import again; the state goes back to ``QUEUED`` first.
    """
    user_id, staged_key = payload.user_id, payload.staged_key
    if not staged_key.startswith(f"{user_id}/"):
        logger.warning(
            "Refused a profile import whose archive is not the user's", extra=core_logger.context(user_id=user_id)
        )
        return

    state = states.get(user_id)
    if state is not None and state.status == _Status.WRITING_FILES:
        logger.error("A profile import died while writing files", extra=core_logger.context(user_id=user_id))
        states.set_status(user_id, _Status.FAILED, failure=_Failure.FILES_INCOMPLETE)
        _discard_staged(staged_key, storage)
        return
    if state is None or state.status not in (_Status.QUEUED, _Status.RUNNING):
        logger.debug("Skipped a profile import that is not pending", extra=core_logger.context(user_id=user_id))
        _discard_staged(staged_key, storage)
        return

    zip_data = storage.get(profile_constants.IMPORT_STAGING_AREA, staged_key)
    if zip_data is None:
        logger.error("The staged profile import is missing", extra=core_logger.context(user_id=user_id))
        states.set_status(user_id, _Status.FAILED, failure=_Failure.PROCESSING_FAILED)
        return

    states.set_status(user_id, _Status.RUNNING)
    committed = False

    def mark_committed() -> None:
        # The marker is what stops a redelivery importing the rows twice, so losing it fails the
        # import (files incomplete) instead of leaving a state that looks safe to run again.
        nonlocal committed
        committed = True
        states.set_status(user_id, _Status.WRITING_FILES, strict=True)

    try:
        imported = _run_importer(user_id, zip_data, storage, mark_committed)
    except Exception as err:
        code = _rejection_code(err)
        if code is None and not committed and will_retry and profile_exceptions.is_transient(err):
            logger.warning(
                "Profile import failed before committing; it will be retried",
                exc_info=err,
                extra=core_logger.context(user_id=user_id),
            )
            states.set_status(user_id, _Status.QUEUED)
            raise
        failure = _Failure.FILES_INCOMPLETE if committed else (code or _Failure.PROCESSING_FAILED)
        log = logger.warning if code is not None else logger.error
        log("Profile import failed", exc_info=err, extra=core_logger.context(user_id=user_id, failure=failure))
        states.set_status(user_id, _Status.FAILED, failure=failure)
        _discard_staged(staged_key, storage)
        return

    states.set_status(user_id, _Status.COMPLETED, imported=imported)
    _discard_staged(staged_key, storage)
    logger.info("Profile data imported", extra=core_logger.context(user_id=user_id, imported=imported))


def sweep_staged_imports(storage: platform_providers.StorageProvider, older_than_seconds: float) -> int:
    """Delete staged archives that no import will read any more.

    The net for a worker that died before it could delete its archive.

    Args:
        storage: The platform storage provider.
        older_than_seconds: A staged archive older than this is removed.

    Returns:
        How many archives were removed.
    """
    cutoff = time.time() - older_than_seconds
    stale = [key for key, modified in storage.iter_objects(profile_constants.IMPORT_STAGING_AREA) if modified < cutoff]
    removed = 0
    for key in stale:
        try:
            storage.delete(profile_constants.IMPORT_STAGING_AREA, key)
        except Exception as err:
            logger.warning("Could not delete a stale staged profile import", exc_info=err)
        else:
            removed += 1
    if removed:
        logger.info("Removed stale staged profile imports", extra=core_logger.context(removed=removed))
    return removed


def discard_staged_imports(user_id: int, storage: platform_providers.StorageProvider) -> None:
    """Delete every archive staged for a user, leaving the sweep to catch them if storage fails.

    Args:
        user_id: The user whose staged archives to remove.
        storage: The platform storage provider.
    """
    try:
        for key in storage.list_keys(profile_constants.IMPORT_STAGING_AREA, f"{user_id}/"):
            storage.delete(profile_constants.IMPORT_STAGING_AREA, key)
    except Exception as err:
        logger.warning(
            "Could not delete a user's staged profile imports", exc_info=err, extra=core_logger.context(user_id=user_id)
        )
