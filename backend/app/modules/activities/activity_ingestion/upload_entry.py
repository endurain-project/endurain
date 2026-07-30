"""Entry point for a file uploaded directly through the API.

Split across the request/background boundary. The request half
(:func:`stage_uploaded_activity_file`) only has to receive bytes: it validates
the filename and extension, hands the upload to the platform storage provider,
and returns a key. Everything CPU-bound — gzip decompression and the format
parse — is in :func:`process_staged_upload`, which runs on a background worker.

That split is the point of the module: parsing a large FIT file takes seconds of
pure CPU, and doing it inline held one of Starlette's shared threadpool tokens
for the duration, so a handful of concurrent uploads could starve every other
request in the process.

The staged blob goes through the ``StorageProvider`` rather than staying on the
receiving node's disk — the same abstraction thumbnails and retained source
files use. Without that, a ``distributed`` deployment running the parse in a
separate ``APP_ROLE=worker`` container could not see the file the API wrote
unless the volume happened to be shared.

Differs from :mod:`bulk_entry` in that the file arrives as an ``UploadFile`` and
has to be streamed to disk before it can be stored.
"""

import gzip
import os
import shutil
import tempfile
import uuid
from pathlib import Path

from fastapi import HTTPException, UploadFile
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

import core.config as core_config
import core.exceptions as core_exceptions
import core.file_uploads as core_file_uploads
import core.logger as core_logger
import infra.runtime as platform_runtime
import modules.activities.activity.schema as activities_schema
import modules.activities.activity_ingestion.pipeline as pipeline
import modules.activities.activity_ingestion.sources as ingestion_sources

logger = core_logger.get_logger(__name__)

# Domain-owned storage namespace for uploads awaiting their parse. For the
# ``local`` backend this maps to ``{DATA_DIR}/activity_files/upload_staging``;
# for S3 it is the object key prefix.
UPLOAD_STAGING_STORAGE_AREA = "activity_files/upload_staging"


def stage_uploaded_activity_file(file: UploadFile) -> str:
    """Validate an upload and hand it to storage, returning its key.

    Runs inside the request. Only the cheap, fail-fast checks live here so the
    client still gets a synchronous 4xx for a file that was never going to
    import — an unsupported extension, a failed signature check, an oversized
    body — rather than a 202 followed by a failure it has to poll for.

    The upload is streamed to a local incoming file first, because that is what
    enforces the byte cap and runs the signature check without holding the whole
    body in memory; only a file that passed is then handed to storage.

    Args:
        file: Incoming FastAPI UploadFile.

    Returns:
        The storage key the upload was staged under.

    Raises:
        InvalidInputError: When the filename is missing.
        UnsupportedFormatError: When the extension is not a supported format.
        HTTPException: When the shared upload validators reject the payload.
    """
    if file.filename is None:
        raise core_exceptions.InvalidInputError("Filename is required")

    # Pre-check the extension so we can short-circuit with a
    # human-friendly 406 before invoking the validator (which would
    # otherwise raise a generic ExtensionSecurityError -> 400).
    _, file_extension = os.path.splitext(file.filename)
    if file_extension.lower() not in core_config.SUPPORTED_FILE_FORMATS:
        raise core_exceptions.UnsupportedFormatError(
            "File extension not supported. Supported file extensions are .gpx, .fit, .tcx and .gz"
        )

    upload_kind = (
        core_file_uploads.UploadKind.GZIP if file_extension.lower() == ".gz" else core_file_uploads.UploadKind.ACTIVITY
    )
    # Server-generated name, used both for the incoming file and as the storage
    # key, so a hostile client filename never reaches either.
    storage_key = f"{uuid.uuid4().hex}{file_extension.lower()}"

    # Validate (signature/size/MIME via safeuploads) and stream
    # the upload to disk in one unified step. The streaming
    # writer enforces the activity/gzip byte cap and writes via
    # a ``.part``-then-rename for atomicity.
    incoming_path = core_file_uploads.save_validated_upload_sync(
        file,
        kind=upload_kind,
        upload_dir=core_config.FILES_UPLOAD_INCOMING_DIR,
        filename=storage_key,
    )
    try:
        platform_runtime.get_active_platform().storage.save(
            UPLOAD_STAGING_STORAGE_AREA,
            storage_key,
            Path(incoming_path).read_bytes(),
        )
    finally:
        core_file_uploads.remove_files([incoming_path])
    return storage_key


def process_staged_upload(
    token_user_id: int,
    staged_key: str,
    db: Session,
) -> list[activities_schema.Activity] | None:
    """Decompress, parse and persist a previously staged upload.

    Runs on a background worker, on any node: the bytes come back from the
    storage provider and are materialised into a private temp directory, because
    the parsers work from a path. The staged blob is removed once it has been
    consumed — including when nothing parsed, since a retry would fail the same
    way.

    Args:
        token_user_id: The user the activities belong to.
        staged_key: Key returned by :func:`stage_uploaded_activity_file`.
        db: Database session.

    Returns:
        List of created Activity schemas, or None if no activity
        could be parsed from the file.

    Raises:
        InvalidInputError: When the staged blob is gone, or a ``.gz``
            decompresses to an unsupported payload.
        ProcessingError: On an internal failure.
    """
    storage = platform_runtime.get_active_platform().storage
    data = storage.get(UPLOAD_STAGING_STORAGE_AREA, staged_key)
    if data is None:
        raise core_exceptions.InvalidInputError("The uploaded file is no longer available")

    _, file_extension = os.path.splitext(staged_key)
    # Private directory so the parsed file cannot collide with another job's,
    # and so its removal is unconditional.
    work_dir = tempfile.mkdtemp(prefix="activity-upload-")
    file_path = os.path.join(work_dir, staged_key)
    Path(file_path).write_bytes(data)
    upload_artifacts: list[str] = [file_path]

    try:
        if file_extension.lower() == ".gz":
            file_path, file_extension = core_file_uploads.decompress_gzip(file_path)
            # ``decompress_gzip`` consumes (removes) the staging .gz and
            # returns the decompressed temp file; track it so a later failure
            # cleans it up.
            upload_artifacts.append(file_path)
            # Re-validate after decompression so the inner payload
            # still matches one of the supported activity formats.
            if file_extension.lower() not in core_config.SUPPORTED_FILE_FORMATS or file_extension.lower() == ".gz":
                raise core_exceptions.InvalidInputError("Decompressed file extension is not supported")
            # Defense in depth: signature-check the inner payload
            # via the same safeuploads validator used for direct
            # activity uploads.
            core_file_uploads.validate_local_file_sync(
                file_path,
                kind=core_file_uploads.UploadKind.ACTIVITY,
            )

        _, file_base_name = os.path.split(file_path)

        created_activities = pipeline.store_activities_from_file(
            token_user_id,
            file_path,
            file_extension,
            file_base_name,
            db,
            source=ingestion_sources.UploadSource(),
        )
        discard_staged_upload(staged_key)
        return created_activities
    except (core_exceptions.DomainError, HTTPException):
        # ``HTTPException`` is still raised by the shared ``core.file_uploads``
        # validators; caught only so the partial artifacts are cleaned up before
        # the error propagates unchanged. The staged blob is deliberately kept:
        # the caller decides whether this failure is terminal or retryable.
        raise
    except (
        OSError,
        EOFError,
        gzip.BadGzipFile,
        shutil.Error,
        SQLAlchemyError,
        ValueError,
        RuntimeError,
        KeyError,
        TypeError,
    ) as err:
        logger.error(
            "Error processing a staged activity upload",
            exc_info=err,
            extra=core_logger.context(user_id=token_user_id),
        )
        raise core_exceptions.ProcessingError() from err
    finally:
        core_file_uploads.remove_files(upload_artifacts)
        shutil.rmtree(work_dir, ignore_errors=True)


def discard_staged_upload(staged_key: str) -> None:
    """Remove a staged upload's blob, ignoring failures.

    Called once a job reaches a terminal state so a rejected or imported upload
    does not leave bytes behind. Best-effort: failing to delete the blob must not
    turn a finished import into a failed one.

    Args:
        staged_key: The storage key to remove.

    Returns:
        None.
    """
    try:
        platform_runtime.get_active_platform().storage.delete(UPLOAD_STAGING_STORAGE_AREA, staged_key)
    except Exception as err:
        logger.warning(
            "Could not remove a staged upload",
            exc_info=err,
            extra=core_logger.context(storage_key=staged_key),
        )
