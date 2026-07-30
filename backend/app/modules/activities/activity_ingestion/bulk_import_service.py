"""Starting a bulk import: scan the user's drop directory, validate, queue.

The route used to hold all of this inline — the directory scan, the
extension filter, the per-file signature validation, the durable-vs-thread-pool
decision, and a bare ``HTTPException(500)`` — which made it the one activities
handler that was not a thin transport adapter, and the one place a domain rule
lived in a router.

Nothing here is transport-aware: it takes a user id and a session, returns how
many files it queued, and raises :mod:`core.exceptions` so the same call works
from a future CLI or scheduled trigger without constructing an HTTP response.
"""

import os
from datetime import UTC, datetime

from fastapi import HTTPException
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

import core.config as core_config
import core.exceptions as core_exceptions
import core.file_uploads as core_file_uploads
import core.logger as core_logger
import modules.activities.activity_ingestion.background as activity_ingestion_background
import modules.activities.activity_ingestion.bulk_import_subscribers as activity_bulk_import_subscribers

logger = core_logger.get_logger(__name__)


def _warn_about_unowned_files(user_id: int) -> None:
    """Warn when importable files sit in the shared root instead of a user directory.

    Bulk import used to scan the shared root, so an existing install can have
    files there that will now be skipped. They are not imported on a guess about
    who owns them — that is the bug this isolation removes — but the operator is
    told exactly where to move them.

    Args:
        user_id: The user whose import was triggered, used to name the target.

    Returns:
        None.
    """
    try:
        stranded = [
            name
            for name in os.listdir(core_config.FILES_BULK_IMPORT_DIR)
            if os.path.isfile(os.path.join(core_config.FILES_BULK_IMPORT_DIR, name))
            and os.path.splitext(name)[1].lower() in core_config.SUPPORTED_FILE_FORMATS
        ]
    except OSError:
        return

    if stranded:
        logger.warning(
            "Skipping bulk-import files in the shared root: they are not attributed to any user",
            extra=core_logger.context(
                console=True,
                user_id=user_id,
                file_count=len(stranded),
                expected_dir=core_config.bulk_import_dir_for(user_id),
            ),
        )


def _collect_importable_files(user_id: int, bulk_import_dir: str) -> list[str]:
    """Return the paths in a user's drop directory that are safe to import.

    A file is skipped (logged, not raised) when it resolves outside the drop
    directory, its extension is unsupported, or its contents fail the signature
    check — one bad file must not stop the import of every other one.

    Args:
        user_id: The owner whose directory is being scanned.
        bulk_import_dir: The user's bulk-import directory.

    Returns:
        Absolute paths of the files that passed validation.
    """
    files_to_process: list[str] = []
    base_dir = os.path.realpath(bulk_import_dir)
    for filename in os.listdir(bulk_import_dir):
        file_path = os.path.join(bulk_import_dir, filename)
        file_extension = os.path.splitext(file_path)[1].lower()

        if file_extension not in core_config.SUPPORTED_FILE_FORMATS:
            logger.info(
                "Skipping a bulk-import file with an unsupported extension",
                extra=core_logger.context(
                    console=True,
                    user_id=user_id,
                    file=os.path.basename(file_path),
                    file_extension=file_extension,
                    supported_extensions=list(core_config.SUPPORTED_FILE_FORMATS),
                ),
            )
            continue

        # Everything downstream opens this path (validation, then staging), so a
        # symlink dropped here would import whatever it points at, anywhere on
        # the server's filesystem. Only entries that resolve to themselves inside
        # the user's own directory are imported.
        if os.path.realpath(file_path) != os.path.join(base_dir, filename):
            logger.warning(
                "Skipping a bulk-import entry that does not resolve inside the user's directory",
                extra=core_logger.context(console=True, user_id=user_id, file=filename),
            )
            continue

        if not os.path.isfile(file_path):
            continue

        try:
            validate_kind = (
                core_file_uploads.UploadKind.GZIP if file_extension == ".gz" else core_file_uploads.UploadKind.ACTIVITY
            )
            core_file_uploads.validate_local_file_sync(file_path, kind=validate_kind)
        except HTTPException as err:
            # The shared upload validator still signals rejection with an
            # HTTPException; a rejected file is skipped, never propagated.
            logger.warning(
                "Skipping a bulk-import file that failed validation",
                extra=core_logger.context(console=True, file=os.path.basename(file_path), reason=err.detail),
            )
            continue

        files_to_process.append(file_path)
        logger.info(
            "Queuing a bulk-import file for processing",
            extra=core_logger.context(console=True, user_id=user_id, file=os.path.basename(file_path)),
        )

    return files_to_process


def start_bulk_import(user_id: int, db: Session) -> int:
    """Queue every importable file in a user's drop directory.

    Each user drops files into their own directory; scanning the shared root
    would import whatever anyone else left there and attribute it to this caller.

    When durable jobs are enabled, one durable job per file is staged in the
    transactional outbox on this session and committed once, then the relay fans
    them into retryable, dead-letterable ``processing_jobs`` rows drained by the
    in-process worker (local) or the worker fleet (distributed) — a crash
    mid-import no longer drops in-flight files, and a failing file retries then
    dead-letters (moved to the import-error dir) instead of vanishing on the
    first error. A staging failure propagates, so the caller is told the files
    were never queued rather than being handed a 202. With durable jobs off
    there is no worker to drain the queue, so the background thread pool owned by
    :mod:`~modules.activities.activity_ingestion.background` runs them instead.

    Args:
        user_id: The owner whose directory to import.
        db: Database session, used to stage the durable jobs.

    Returns:
        How many files were queued.

    Raises:
        ProcessingError: When the directory cannot be read or the jobs cannot be
            queued.
    """
    import_time = datetime.now(UTC).isoformat()
    logger.info(
        "Bulk import initiated",
        extra=core_logger.context(console=True, user_id=user_id, import_time=import_time),
    )

    try:
        bulk_import_dir = core_config.bulk_import_dir_for(user_id)
        os.makedirs(bulk_import_dir, exist_ok=True)
        _warn_about_unowned_files(user_id)

        files_to_process = _collect_importable_files(user_id, bulk_import_dir)

        if core_config.settings.JOBS_ENABLED:
            activity_bulk_import_subscribers.publish_bulk_import_files(files_to_process, user_id, import_time, db)
        else:
            activity_ingestion_background.submit_bulk_import(user_id, files_to_process, import_time)
    except (OSError, RuntimeError, SQLAlchemyError) as err:
        logger.error(
            "Error starting the bulk import",
            exc_info=err,
            extra=core_logger.context(user_id=user_id),
        )
        raise core_exceptions.ProcessingError() from err

    logger.info(
        "Bulk import queued; processing continues in the background",
        extra=core_logger.context(console=True, user_id=user_id, file_count=len(files_to_process)),
    )
    return len(files_to_process)
