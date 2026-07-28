"""Entry point for a file uploaded directly through the API.

Differs from the background entry in :mod:`bulk_entry` in two ways: the file
arrives as an ``UploadFile`` and has to be streamed to disk before it can be
parsed, and a failure is **raised** as an ``HTTPException`` (the upload route's
contract) rather than swallowed, after any partial artifacts are cleaned up.
"""

import gzip
import os
import shutil
import uuid

from fastapi import HTTPException, UploadFile
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

import core.config as core_config
import core.exceptions as core_exceptions
import core.file_uploads as core_file_uploads
import core.logger as core_logger
import modules.activities.activity.schema as activities_schema
import modules.activities.activity_ingestion.pipeline as pipeline
import modules.activities.activity_ingestion.sources as ingestion_sources

logger = core_logger.get_logger(__name__)


def store_uploaded_activity_file(
    token_user_id: int,
    file: UploadFile,
    db: Session,
) -> list[activities_schema.Activity] | None:
    """Persist an uploaded activity file and return the created activities.

    Validates the filename and extension, streams the upload to disk, decompresses
    ``.gz`` payloads, then delegates to the shared pipeline. On failure it removes
    any partial upload artifacts and re-raises.

    Args:
        token_user_id: Authenticated user ID.
        file: Incoming FastAPI UploadFile.
        db: Database session.

    Returns:
        List of created Activity schemas, or None if no activity
        could be parsed from the file.

    Raises:
        InvalidInputError: When the filename is missing or a ``.gz`` decompresses
            to an unsupported payload.
        UnsupportedFormatError: When the extension is not a supported format.
        ProcessingError: On an internal failure.
    """
    # Validate filename exists
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

    upload_dir = core_config.settings.FILES_DIR
    upload_kind = (
        core_file_uploads.UploadKind.GZIP if file_extension.lower() == ".gz" else core_file_uploads.UploadKind.ACTIVITY
    )
    # Server-generated filename to defeat path traversal and collisions.
    storage_name = f"{uuid.uuid4().hex}{file_extension.lower()}"
    upload_artifacts: list[str] = []

    try:
        # Validate (signature/size/MIME via safeuploads) and stream
        # the upload to disk in one unified step. The streaming
        # writer enforces the activity/gzip byte cap and writes via
        # a ``.part``-then-rename for atomicity.
        file_path = core_file_uploads.save_validated_upload_sync(
            file,
            kind=upload_kind,
            upload_dir=upload_dir,
            filename=storage_name,
        )
        upload_artifacts.append(file_path)

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

        # Delegate to the shared ingestion pipeline. The upload route is
        # synchronous, so Starlette already runs it on a threadpool worker.
        created_activities = pipeline.store_activities_from_file(
            token_user_id,
            file_path,
            file_extension,
            file_base_name,
            db,
            source=ingestion_sources.UploadSource(),
        )
        if created_activities is None:
            core_file_uploads.remove_files(upload_artifacts)
        return created_activities
    except (core_exceptions.DomainError, HTTPException):
        # ``HTTPException`` is still raised by the shared ``core.file_uploads``
        # validators; caught only so the partial artifacts are cleaned up before
        # the error propagates unchanged.
        core_file_uploads.remove_files(upload_artifacts)
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
            "Error in store_uploaded_activity_file",
            exc_info=err,
            extra=core_logger.context(user_id=token_user_id),
        )
        core_file_uploads.remove_files(upload_artifacts)
        raise core_exceptions.ProcessingError() from err
