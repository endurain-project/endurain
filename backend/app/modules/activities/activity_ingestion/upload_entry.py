"""Entry point for a file uploaded directly through the API.

Split across the request/background boundary. The request half
(:func:`stage_uploaded_activity_file`) only has to receive bytes: it validates
the filename and extension, streams the upload to the staging directory, and
returns. Everything CPU-bound — gzip decompression and the format parse — is in
:func:`process_staged_upload`, which runs on a background worker.

That split is the point of the module: parsing a large FIT file takes seconds of
pure CPU, and doing it inline held one of Starlette's shared threadpool tokens
for the duration, so a handful of concurrent uploads could starve every other
request in the process.

Differs from :mod:`bulk_entry` in that the file arrives as an ``UploadFile`` and
has to be streamed to disk before it can be parsed.
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


def stage_uploaded_activity_file(file: UploadFile) -> str:
    """Validate an upload and stream it to the staging directory.

    Runs inside the request. Only the cheap, fail-fast checks live here so the
    client still gets a synchronous 4xx for a file that was never going to
    import — an unsupported extension, a failed signature check, an oversized
    body — rather than a 202 followed by a failure it has to poll for.

    Args:
        file: Incoming FastAPI UploadFile.

    Returns:
        Absolute path of the staged file.

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
    # Server-generated filename to defeat path traversal and collisions.
    storage_name = f"{uuid.uuid4().hex}{file_extension.lower()}"

    # Validate (signature/size/MIME via safeuploads) and stream
    # the upload to disk in one unified step. The streaming
    # writer enforces the activity/gzip byte cap and writes via
    # a ``.part``-then-rename for atomicity.
    return core_file_uploads.save_validated_upload_sync(
        file,
        kind=upload_kind,
        upload_dir=core_config.FILES_UPLOAD_STAGING_DIR,
        filename=storage_name,
    )


def process_staged_upload(
    token_user_id: int,
    staged_path: str,
    db: Session,
) -> list[activities_schema.Activity] | None:
    """Decompress, parse and persist a previously staged upload.

    Runs on a background worker. Confines the path to the staging directory
    before touching it, so a job whose stored path was tampered with cannot make
    the parser read an arbitrary file.

    Args:
        token_user_id: The user the activities belong to.
        staged_path: Path returned by :func:`stage_uploaded_activity_file`.
        db: Database session.

    Returns:
        List of created Activity schemas, or None if no activity
        could be parsed from the file.

    Raises:
        InvalidInputError: When a ``.gz`` decompresses to an unsupported payload.
        ProcessingError: On an internal failure.
    """
    file_path = str(core_file_uploads.ensure_within(staged_path, core_config.FILES_UPLOAD_STAGING_DIR))
    _, file_extension = os.path.splitext(file_path)
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
            "Error processing a staged activity upload",
            exc_info=err,
            extra=core_logger.context(user_id=token_user_id),
        )
        core_file_uploads.remove_files(upload_artifacts)
        raise core_exceptions.ProcessingError() from err
