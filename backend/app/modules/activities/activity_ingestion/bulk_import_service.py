"""Bulk import: one job over one staged archive, worked through in batches.

A bulk import is a ZIP of activity files, either uploaded or built from a folder the
user dropped files into on the server. The archive is staged in the platform
``StorageProvider`` and one job row tracks it, so the request that starts an import
does constant work however many files it holds, and any worker can run it.

The job is processed in short batches rather than as one long task. Each batch
imports files until a time or count budget is spent, records how far it got on the
job row and, on the durable profile, queues its own continuation in the same
transaction, which sends it to the back of the queue. A large import therefore
interleaves with everyone else's work instead of holding a worker, never outlives a
job lease, and resumes from its cursor after a crash. Importing a file is idempotent
(a content-derived dedup key), so a batch that is repeated after a crash costs
nothing but time.

Without durable jobs there is no queue to yield to, so the same batch runs once with
no budget on the in-process pool.

Provider exports register a :class:`BulkImportFormat`; this module names none.
"""

import os
import tempfile
import time
import uuid
import zipfile

import jasil.providers as platform_providers
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

import core.config as core_config
import core.database as core_database
import core.exceptions as core_exceptions
import core.file_uploads as core_file_uploads
import core.logger as core_logger
import modules.activities.activity_ingestion.constants as activity_ingestion_constants
import modules.activities.activity_ingestion.contracts as activity_ingestion_contracts
import modules.activities.activity_ingestion.crud as activity_ingestion_crud
import modules.activities.activity_ingestion.dispatch_service as activity_ingestion_dispatch_service
import modules.activities.activity_ingestion.event_publishers as activity_ingestion_event_publishers
import modules.activities.activity_ingestion.pipeline_service as activity_ingestion_pipeline_service
import modules.activities.activity_ingestion.provider_registry as activity_ingestion_provider_registry
import modules.activities.activity_ingestion.schema as activity_ingestion_schema
import modules.activities.activity_ingestion.service as activity_ingestion_service
import modules.activities.activity_ingestion.staging as activity_ingestion_staging
import modules.activities.activity_ingestion.upload_entry_service as activity_ingestion_upload_entry_service

logger = core_logger.get_logger(__name__)

GENERIC_FORMAT_NAME = "generic"

#: Where the bytes of a file that could not be imported are kept for the operator.
BULK_IMPORT_ERROR_STORAGE_AREA = "bulk_import_errors"

_ARCHIVE_KEY_PREFIX = "bulk-"

# One batch: stop at whichever comes first. The time budget is a fraction of the
# job lease, so a batch can never be mistaken for a dead worker.
_BATCH_MAX_FILES = 200
_PROGRESS_EVERY_FILES = 10
_MIN_BATCH_SECONDS = 30
_LEASE_FRACTION = 3


def _is_supported_member(member_name: str) -> bool:
    """Whether an archive member is an activity file the generic format imports.

    Args:
        member_name: The member's path inside the archive.

    Returns:
        True for a file with a supported extension that is not OS metadata.
    """
    base = os.path.basename(member_name)
    if not base or base.startswith(".") or member_name.startswith("__MACOSX/"):
        return False
    return os.path.splitext(base)[1].lower() in core_config.SUPPORTED_FILE_FORMATS


def _generic_format() -> activity_ingestion_contracts.BulkImportFormat:
    """Build the built-in format: every supported file, no manifest.

    Returns:
        The generic format.
    """
    return activity_ingestion_contracts.BulkImportFormat(
        name=GENERIC_FORMAT_NAME,
        is_activity_member=_is_supported_member,
        is_export_member=_is_supported_member,
        drop_directory=core_config.bulk_import_dir_for,
        build_source=lambda user_id, import_initiated_time, _read_member: activity_ingestion_contracts.BulkImportSource(
            import_initiated_time=import_initiated_time, user_id=user_id
        ),
    )


def resolve_format(name: str) -> activity_ingestion_contracts.BulkImportFormat:
    """Return the bulk-import format registered under a name.

    Args:
        name: The format identifier a client selected.

    Returns:
        The format.

    Raises:
        InvalidInputError: When no such format is registered in this process.
    """
    if name == GENERIC_FORMAT_NAME:
        return _generic_format()
    found = activity_ingestion_provider_registry.get_bulk_format(name)
    if found is None:
        raise core_exceptions.InvalidInputError("Unknown bulk import source")
    return found


def _archive_key(job_id: str) -> str:
    """Return the staged-upload key a job's archive is held under.

    Args:
        job_id: The bulk-import job.

    Returns:
        The key, in the staged-upload namespace so the stale-job reaper and the
        staged-blob sweep cover it like any other staged upload.
    """
    return f"{_ARCHIVE_KEY_PREFIX}{job_id}.zip"


def _ensure_none_running(user_id: int, db: Session) -> None:
    """Refuse a second bulk import while the user has one running.

    Args:
        user_id: The requesting user.
        db: Database session.

    Raises:
        ConflictError: When an import is already running.
    """
    if activity_ingestion_crud.get_active_bulk_import_job_id(user_id, db) is not None:
        raise core_exceptions.ConflictError("A bulk import is already running")


def accept_archive(
    user_id: int,
    filename: str | None,
    save_upload: activity_ingestion_upload_entry_service.UploadSaver,
    source: str,
    storage: platform_providers.StorageProvider,
    db: Session,
) -> activity_ingestion_schema.ActivityIngestionJobRead:
    """Stage an uploaded archive and queue it for import.

    The request validates the archive's shape from its directory listing only; no
    member is read. The import itself runs on a worker.

    Args:
        user_id: The importing user.
        filename: The client-supplied filename.
        save_upload: Validates the request's upload and streams it to local disk.
        source: The archive format to read (``generic`` or a provider export).
        storage: The blob-storage provider the archive is staged in.
        db: Database session.

    Returns:
        The accepted import, in the pending state.

    Raises:
        InvalidInputError: For an unknown source, a non-ZIP name or an archive
            with nothing importable.
        ConflictError: When the user already has an import running.
        DomainError: When the shared upload validators or the archive caps reject it.
    """
    bulk_format = resolve_format(source)
    if filename is None or os.path.splitext(filename)[1].lower() != ".zip":
        raise core_exceptions.InvalidInputError("A bulk import takes a .zip archive")
    _ensure_none_running(user_id, db)

    incoming_path = save_upload(
        kind=core_file_uploads.UploadKind.ZIP,
        upload_dir=core_config.FILES_UPLOAD_INCOMING_DIR,
        filename=f"{uuid.uuid4().hex}.zip",
    )
    job_id = str(uuid.uuid4())
    key = _archive_key(job_id)
    try:
        members = core_file_uploads.list_zip_members(incoming_path)
        files_total = sum(1 for member in members if bulk_format.is_activity_member(member.name))
        if files_total == 0:
            raise core_exceptions.InvalidInputError("The archive contains no importable files")
        with open(incoming_path, "rb") as handle:
            storage.save_stream(
                activity_ingestion_upload_entry_service.UPLOAD_STAGING_STORAGE_AREA,
                activity_ingestion_upload_entry_service.upload_staging_storage_key(key),
                handle,
            )
    finally:
        core_file_uploads.remove_files([incoming_path])

    try:
        activity_ingestion_crud.create_ingestion_job(
            job_id,
            user_id,
            activity_ingestion_constants.IngestionJobKind.BULK_IMPORT,
            db,
            filename=filename,
            staged_key=key,
            import_source=bulk_format.name,
            files_total=files_total,
        )
        activity_ingestion_dispatch_service.commit_or_publish(
            db,
            publish=lambda commit: activity_ingestion_event_publishers.publish_bulk_import_continue(
                job_id, user_id, db, commit=commit
            ),
        )
    except IntegrityError as err:
        # Two requests passed the check above together; the partial unique index
        # decides which one runs.
        db.rollback()
        activity_ingestion_upload_entry_service.discard_staged_upload(key, storage)
        raise core_exceptions.ConflictError("A bulk import is already running") from err
    except Exception:
        activity_ingestion_upload_entry_service.discard_staged_upload(key, storage)
        raise

    activity_ingestion_dispatch_service.run_in_background(run_bulk_import_job, job_id, storage)
    logger.info(
        "Bulk import accepted",
        extra=core_logger.context(console=True, user_id=user_id, job_id=job_id, files=files_total),
    )
    return _job_view(job_id, user_id, db)


def start_from_directory(
    user_id: int,
    source: str,
    storage: platform_providers.StorageProvider,
    db: Session,
) -> activity_ingestion_schema.ActivityIngestionJobRead:
    """Queue an import of the files in the user's server-side import folder.

    The request only checks the folder holds something importable and records the
    job. Packing the folder into an archive and staging it needs the folder, which
    only this node can see, so that runs on this node's in-process pool in every
    profile; everything after it is node-independent.

    Args:
        user_id: The importing user.
        source: The archive format the folder holds.
        storage: The blob-storage provider.
        db: Database session.

    Returns:
        The accepted import, in the pending state.

    Raises:
        InvalidInputError: For an unknown source or an empty folder.
        ConflictError: When the user already has an import running.
    """
    bulk_format = resolve_format(source)
    _ensure_none_running(user_id, db)
    directory = bulk_format.drop_directory(user_id)
    os.makedirs(directory, exist_ok=True)
    if not _folder_has_importable_file(directory, bulk_format):
        raise core_exceptions.InvalidInputError("There is nothing to import in your import folder")

    job_id = str(uuid.uuid4())
    try:
        activity_ingestion_crud.create_ingestion_job(
            job_id,
            user_id,
            activity_ingestion_constants.IngestionJobKind.BULK_IMPORT,
            db,
            import_source=bulk_format.name,
        )
        db.commit()
    except IntegrityError as err:
        db.rollback()
        raise core_exceptions.ConflictError("A bulk import is already running") from err

    activity_ingestion_dispatch_service.run_on_this_node(
        feed_archive_from_directory, job_id, user_id, bulk_format.name, directory, storage
    )
    logger.info(
        "Bulk import from the import folder accepted",
        extra=core_logger.context(console=True, user_id=user_id, job_id=job_id),
    )
    return _job_view(job_id, user_id, db)


def _folder_has_importable_file(directory: str, bulk_format: activity_ingestion_contracts.BulkImportFormat) -> bool:
    """Whether a folder holds at least one activity file of the format.

    Args:
        directory: The user's import folder.
        bulk_format: The format deciding what counts.

    Returns:
        True as soon as one is found.
    """
    for root, _dirs, files in os.walk(directory, followlinks=False):
        for name in files:
            relative = os.path.relpath(os.path.join(root, name), directory).replace(os.sep, "/")
            if bulk_format.is_activity_member(relative):
                return True
    return False


def feed_archive_from_directory(
    job_id: str,
    user_id: int,
    source: str,
    directory: str,
    storage: platform_providers.StorageProvider,
) -> None:
    """Pack a user's import folder into the job's archive, stage it, and start it.

    The originals are removed only once the job that owns the staged archive is
    committed, so a failure leaves the user's files where they put them.

    Args:
        job_id: The bulk-import job to attach the archive to.
        user_id: The importing user.
        source: The archive format the folder holds.
        directory: The folder to pack.
        storage: The blob-storage provider.
    """
    packed: list[str] = []
    try:
        bulk_format = resolve_format(source)
        key = _archive_key(job_id)
        with tempfile.TemporaryDirectory(prefix="bulk-import-pack-") as work_dir:
            archive_path = os.path.join(work_dir, "import.zip")
            files_total = _pack_directory(directory, archive_path, bulk_format, packed)
            core_file_uploads.list_zip_members(archive_path)
            with open(archive_path, "rb") as handle:
                storage.save_stream(
                    activity_ingestion_upload_entry_service.UPLOAD_STAGING_STORAGE_AREA,
                    activity_ingestion_upload_entry_service.upload_staging_storage_key(key),
                    handle,
                )
        with core_database.SessionLocal() as db:
            activity_ingestion_crud.attach_bulk_archive(job_id, key, files_total, db)
            activity_ingestion_dispatch_service.commit_or_publish(
                db,
                publish=lambda commit: activity_ingestion_event_publishers.publish_bulk_import_continue(
                    job_id, user_id, db, commit=commit
                ),
            )
    except Exception as err:
        logger.error(
            "Could not stage the bulk import folder",
            exc_info=err,
            extra=core_logger.context(console=True, user_id=user_id, job_id=job_id),
        )
        activity_ingestion_service.fail_ingestion_job(
            job_id,
            activity_ingestion_constants.IngestionJobErrorCode.PROCESSING_FAILED,
            storage,
            _archive_key(job_id),
        )
        return

    # Only now does the staged archive own the files, so consuming them is safe.
    for path in packed:
        try:
            os.remove(path)
        except OSError as err:
            logger.warning(
                "Bulk import: staged a file but could not remove the original",
                exc_info=err,
                extra=core_logger.context(console=True, user_id=user_id, file=os.path.basename(path)),
            )

    if not activity_ingestion_dispatch_service.worker_retries():
        run_bulk_import_job(job_id, storage)


def _pack_directory(
    directory: str,
    archive_path: str,
    bulk_format: activity_ingestion_contracts.BulkImportFormat,
    packed: list[str],
) -> int:
    """Zip the export's files in a folder, refusing links and anything outside it.

    Args:
        directory: The folder to pack.
        archive_path: Where to write the archive.
        bulk_format: The format deciding which members count as activity files.
        packed: Receives the absolute path of every file written.

    Returns:
        The number of importable files packed.

    Raises:
        PayloadTooLargeError: When the folder exceeds the archive caps.
    """
    base = os.path.realpath(directory)
    total_bytes = 0
    importable = 0
    with zipfile.ZipFile(archive_path, "w", zipfile.ZIP_DEFLATED) as archive:
        for root, _dirs, files in os.walk(directory, followlinks=False):
            for name in sorted(files):
                path = os.path.join(root, name)
                # A symlink would import whatever it points at, anywhere on the
                # server; only entries that resolve to themselves inside the
                # folder are packed.
                if os.path.islink(path) or os.path.realpath(path) != os.path.join(
                    base, os.path.relpath(path, directory)
                ):
                    continue
                relative = os.path.relpath(path, directory).replace(os.sep, "/")
                if not bulk_format.is_export_member(relative):
                    continue
                total_bytes += os.path.getsize(path)
                if total_bytes > core_file_uploads.MAX_ARCHIVE_UNCOMPRESSED_BYTES or len(packed) >= (
                    core_file_uploads.MAX_ARCHIVE_MEMBERS
                ):
                    raise core_exceptions.PayloadTooLargeError("The import folder is too large for one import")
                archive.write(path, arcname=relative)
                packed.append(path)
                if bulk_format.is_activity_member(relative):
                    importable += 1
    return importable


def _job_view(job_id: str, user_id: int, db: Session) -> activity_ingestion_schema.ActivityIngestionJobRead:
    """Read an accepted job back for the response.

    Args:
        job_id: The job identifier.
        user_id: The owner.
        db: Database session.

    Returns:
        The job's read view.
    """
    job = activity_ingestion_crud.get_ingestion_job(job_id, user_id, db)
    if job is None:
        raise core_exceptions.ProcessingError()
    return job


def run_bulk_import_job(job_id: str, storage: platform_providers.StorageProvider) -> None:
    """Work one batch of a bulk import, recording the outcome on the job row.

    The job body for both executors. On the durable profile a batch that leaves
    files over has already queued its continuation, in the same transaction that
    recorded its progress, and returns so the worker is free; otherwise the single
    unbudgeted pass finishes the import.

    Args:
        job_id: The ``activity_ingestion_jobs`` row to continue.
        storage: The blob-storage provider the archive is staged in.

    Raises:
        Exception: Whatever the batch raised, so the durable runner can retry.
    """
    try:
        _run_batch(job_id, storage)
    except Exception:
        if not activity_ingestion_dispatch_service.worker_retries():
            activity_ingestion_service.fail_ingestion_job(
                job_id, activity_ingestion_constants.IngestionJobErrorCode.PROCESSING_FAILED, storage
            )
        else:
            activity_ingestion_service.release_ingestion_job(job_id)
        raise


def _batch_budget() -> tuple[int, float | None]:
    """Return the file and time budget of one batch for the active profile.

    Returns:
        ``(max_files, seconds)``; ``seconds`` is ``None`` when nothing re-queues a
        batch, so it has to run to the end.
    """
    if not activity_ingestion_dispatch_service.worker_retries():
        return 10**9, None
    lease = core_config.settings.JOBS_LEASE_SECONDS
    return _BATCH_MAX_FILES, float(max(_MIN_BATCH_SECONDS, lease // _LEASE_FRACTION))


def _run_batch(job_id: str, storage: platform_providers.StorageProvider) -> None:
    """Import files from the job's archive until the batch budget is spent.

    Args:
        job_id: The job to continue.
        storage: The blob-storage provider.
    """
    with core_database.SessionLocal() as db:
        state = activity_ingestion_crud.get_bulk_import_state(job_id, db)
        if state is None or state.finished:
            logger.debug("Skipping a bulk import that is unknown or finished", extra=core_logger.context(job_id=job_id))
            return
        if state.staged_key is None:
            # The folder is still being packed; the continuation is queued once it is.
            return
        if not activity_ingestion_crud.mark_processing(
            job_id, db, lease=activity_ingestion_dispatch_service.claim_lease()
        ):
            logger.debug(
                "Skipping a bulk import batch that is claimed elsewhere", extra=core_logger.context(job_id=job_id)
            )
            return
        db.commit()

    try:
        bulk_format = resolve_format(state.import_source)
    except core_exceptions.InvalidInputError:
        activity_ingestion_service.fail_ingestion_job(
            job_id, activity_ingestion_constants.IngestionJobErrorCode.PROCESSING_FAILED, storage, state.staged_key
        )
        return

    max_files, seconds = _batch_budget()
    deadline = None if seconds is None else time.monotonic() + seconds

    with tempfile.TemporaryDirectory(prefix="bulk-import-") as work_dir:
        archive_path = os.path.join(work_dir, "archive.zip")
        if not activity_ingestion_staging.copy_blob_to_path(
            activity_ingestion_upload_entry_service.UPLOAD_STAGING_STORAGE_AREA,
            activity_ingestion_upload_entry_service.upload_staging_storage_key(state.staged_key),
            archive_path,
            storage,
        ):
            activity_ingestion_service.fail_ingestion_job(
                job_id, activity_ingestion_constants.IngestionJobErrorCode.INVALID_FILE, storage, state.staged_key
            )
            return

        members = sorted(
            member.name
            for member in core_file_uploads.list_zip_members(archive_path)
            if bulk_format.is_activity_member(member.name)
        )
        pending = [name for name in members if state.cursor is None or name > state.cursor]

        with zipfile.ZipFile(archive_path) as archive:
            try:
                source = bulk_format.build_source(state.user_id, state.created_at.isoformat(), _member_reader(archive))
            except core_exceptions.DomainError as err:
                logger.error(
                    "Bulk import archive is not a valid export",
                    extra=core_logger.context(console=True, job_id=job_id, reason=err.detail),
                )
                activity_ingestion_service.fail_ingestion_job(
                    job_id, activity_ingestion_service.error_code_for(err), storage, state.staged_key
                )
                return

            done, failed, cursor, handled = state.files_done, state.files_failed, state.cursor, 0
            for name in pending:
                if handled >= max_files or (deadline is not None and time.monotonic() >= deadline):
                    break
                if _import_member(archive, name, state.user_id, source, job_id, storage):
                    done += 1
                else:
                    failed += 1
                cursor = name
                handled += 1
                if handled % _PROGRESS_EVERY_FILES == 0:
                    _save_progress(job_id, cursor, done, failed)

    if handled < len(pending):
        _checkpoint_and_continue(job_id, state.user_id, cursor, done, failed)
        return

    with core_database.SessionLocal() as db:
        activity_ingestion_crud.mark_bulk_completed(job_id, cursor, done, failed, db)
        db.commit()
    activity_ingestion_upload_entry_service.discard_staged_upload(state.staged_key, storage)
    logger.info(
        "Bulk import finished",
        extra=core_logger.context(console=True, user_id=state.user_id, job_id=job_id, done=done, failed=failed),
    )


def _member_reader(archive: zipfile.ZipFile) -> activity_ingestion_contracts.ArchiveMemberReader:
    """Build the reader a format uses to reach its manifest and sidecar files.

    Args:
        archive: The open archive.

    Returns:
        A callable returning a member's bytes, or ``None`` when it is absent.
    """

    def read(member_name: str) -> bytes | None:
        try:
            info = archive.getinfo(member_name)
        except KeyError:
            return None
        if info.file_size > core_file_uploads.MAX_READ_MEMBER_BYTES:
            raise core_exceptions.PayloadTooLargeError("Archive entry exceeds the allowed size")
        return archive.read(info)

    return read


def _import_member(
    archive: zipfile.ZipFile,
    member_name: str,
    user_id: int,
    source: activity_ingestion_contracts.BulkImportSource,
    job_id: str,
    storage: platform_providers.StorageProvider,
) -> bool:
    """Import one archive member, never raising: one bad file must not stop the rest.

    Args:
        archive: The open archive.
        member_name: The member to import.
        user_id: The importing user.
        source: The source applied to the file.
        job_id: The job, for the error trail.
        storage: The blob-storage provider.

    Returns:
        True when the file was imported (or was already), False when it failed.
    """
    base_name = os.path.basename(member_name)
    with tempfile.TemporaryDirectory(prefix="bulk-member-") as member_dir:
        # The member's own directory keeps its base name intact, which the Strava
        # manifest and the Garmin activity id are keyed by, and means two members
        # with the same name in different folders cannot collide.
        path = os.path.join(member_dir, base_name)
        try:
            core_file_uploads.copy_zip_member(archive, member_name, path)
            with core_database.SessionLocal() as db:
                activity_ingestion_pipeline_service.validate_prepare_and_store_file(
                    user_id, path, db, source=source, storage=storage
                )
        except Exception as err:
            logger.error(
                "Bulk import: a file could not be imported",
                exc_info=err,
                extra=core_logger.context(console=True, user_id=user_id, job_id=job_id, file=base_name),
            )
            _keep_failed_member(archive, member_name, user_id, job_id, storage)
            return False
    return True


def _keep_failed_member(
    archive: zipfile.ZipFile,
    member_name: str,
    user_id: int,
    job_id: str,
    storage: platform_providers.StorageProvider,
) -> None:
    """Keep a failed file's bytes where the operator can recover them.

    Args:
        archive: The open archive.
        member_name: The member that failed.
        user_id: The importing user.
        job_id: The job.
        storage: The blob-storage provider.
    """
    try:
        with tempfile.TemporaryDirectory(prefix="bulk-failed-") as work_dir:
            path = os.path.join(work_dir, "member")
            core_file_uploads.copy_zip_member(archive, member_name, path)
            with open(path, "rb") as handle:
                storage.save_stream(
                    BULK_IMPORT_ERROR_STORAGE_AREA,
                    f"{int(user_id)}/{job_id}/{os.path.basename(member_name)}",
                    handle,
                )
    except Exception as err:
        logger.warning(
            "Bulk import: could not keep a failed file",
            exc_info=err,
            extra=core_logger.context(console=True, user_id=user_id, job_id=job_id),
        )


def _save_progress(job_id: str, cursor: str | None, done: int, failed: int) -> None:
    """Record a bulk import's resume point in its own short transaction.

    Args:
        job_id: The job identifier.
        cursor: The last member handled.
        done: Files imported so far.
        failed: Files that failed.
    """
    with core_database.SessionLocal() as db:
        activity_ingestion_crud.record_bulk_progress(job_id, cursor, done, failed, db)
        db.commit()
    logger.debug("Bulk import progress saved", extra=core_logger.context(job_id=job_id, done=done, failed=failed))


def _checkpoint_and_continue(job_id: str, user_id: int, cursor: str | None, done: int, failed: int) -> None:
    """End a batch that left files over: record progress and queue the next batch.

    On the durable profile the progress and the continuation event are one
    transaction. Without durable jobs the budget is unbounded, so a batch only
    reaches here if it stopped for another reason, and the next scheduled attempt
    is the stale-job reaper.

    Args:
        job_id: The job identifier.
        user_id: The importing user.
        cursor: The last member handled.
        done: Files imported so far.
        failed: Files that failed.
    """
    with core_database.SessionLocal() as db:
        activity_ingestion_crud.record_bulk_progress(job_id, cursor, done, failed, db, release=True)
        activity_ingestion_dispatch_service.commit_or_publish(
            db,
            publish=lambda commit: activity_ingestion_event_publishers.publish_bulk_import_continue(
                job_id, user_id, db, commit=commit
            ),
        )
    logger.debug("Bulk import batch finished; continuation queued", extra=core_logger.context(job_id=job_id))
