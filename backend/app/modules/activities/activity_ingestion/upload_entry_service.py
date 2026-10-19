"""Entry point for a file uploaded directly through the API.

Split across the request/background boundary. The request half
(:func:`receive_upload` then :func:`store_received_upload`) only has to receive bytes: it validates
the filename and extension, hands the upload to the platform storage provider,
and returns a key. Everything CPU-bound — gzip decompression and the format
parse — is in :func:`process_staged_upload`, which runs on a background worker.

That split is the point of the module: parsing a large FIT file takes seconds of
pure CPU, and doing it inline would hold one of Starlette's shared threadpool tokens
for the duration, so a handful of concurrent uploads could starve every other
request in the process.

The staged blob goes through the ``StorageProvider`` rather than staying on the
receiving node's disk — the same abstraction thumbnails and retained source
files use. Without that, a ``distributed`` deployment running the parse in a
separate ``APP_ROLE=worker`` container could not see the file the API wrote
unless the volume happened to be shared.

Differs from :mod:`provider_entry_service` in that the file arrives in the request
and has to be streamed to disk before it can be stored.
"""

import gzip
import os
import shutil
import tempfile
import uuid
from dataclasses import dataclass
from typing import Protocol

import jasil.providers as platform_providers
from sqlalchemy.orm import Session

import core.config as core_config
import core.exceptions as core_exceptions
import core.file_uploads as core_file_uploads
import core.logger as core_logger
import modules.activities.activity.schema as activity_schema
import modules.activities.activity_file_storage.constants as activity_file_storage_constants
import modules.activities.activity_ingestion.contracts as activity_ingestion_contracts
import modules.activities.activity_ingestion.pipeline_service as activity_ingestion_pipeline_service
import modules.activities.activity_ingestion.staging as activity_ingestion_staging

logger = core_logger.get_logger(__name__)

# Domain-owned storage namespace for uploads awaiting their parse. The staging
# hierarchy belongs in the key because JASIL storage areas are single path
# components.
UPLOAD_STAGING_STORAGE_AREA = activity_file_storage_constants.ACTIVITY_FILE_STORAGE_AREA
UPLOAD_STAGING_KEY_PREFIX = "upload_staging/"


def upload_staging_storage_key(key: str) -> str:
    """Build the storage key a staged upload is held under.

    Args:
        key: The staged upload's key.

    Returns:
        The prefixed storage key.
    """
    return f"{UPLOAD_STAGING_KEY_PREFIX}{key}"


@dataclass(frozen=True)
class ReceivedUpload:
    """An upload that passed validation and is on local disk, not yet stored.

    Attributes:
        incoming_path: Local file holding the received bytes.
        storage_key: Server-generated key the upload will be stored under.
        fingerprint: SHA-256 of the received bytes, used to tell a genuine
            replay from a reused idempotency key carrying a different file.
            ``None`` when the caller sent no key, since nothing would read it.
    """

    incoming_path: str
    storage_key: str
    fingerprint: str | None = None


class UploadSaver(Protocol):
    """Callable that validates the request's upload and streams it to local disk."""

    def __call__(self, *, kind: core_file_uploads.UploadKind, upload_dir: str, filename: str) -> str:
        """Validate the upload and save it as ``upload_dir/filename``.

        The router binds the request's file to the shared upload writer and
        passes the result down, so nothing below the router handles the
        transport's file object.

        Args:
            kind: Logical content type, which drives the validator and size cap.
            upload_dir: Trusted destination directory.
            filename: Server-generated filename within ``upload_dir``.

        Returns:
            Absolute filesystem path of the saved file.
        """
        ...


def receive_upload(filename: str | None, save_upload: UploadSaver, *, fingerprint: bool = False) -> ReceivedUpload:
    """Validate an upload, stream it to local disk, and read it back.

    The first of the two staging phases. Split from :func:`store_received_upload`
    so the caller can decide *between* them — an idempotent replay needs the
    fingerprint to verify the request matches, but must not pay for the storage
    write.

    Only the cheap, fail-fast checks live here so the client still gets a
    synchronous 4xx for a file that was never going to import — an unsupported
    extension, a failed signature check, an oversized body — rather than a 202
    followed by a failure it has to poll for.

    Args:
        filename: The client-supplied filename, read for its extension only.
        save_upload: Validates the request's upload and streams it to disk.
        fingerprint: Whether to hash the payload. Only worth it when the caller
            supplied an idempotency key, because nothing else reads it.

    Returns:
        The received upload, still local.

    Raises:
        InvalidInputError: When the filename is missing.
        UnsupportedFormatError: When the extension is not a supported format.
        DomainError: When the shared upload validators reject the payload.
    """
    if filename is None:
        raise core_exceptions.InvalidInputError("Filename is required")

    # Pre-check the extension so we can short-circuit with a
    # human-friendly 406 before invoking the validator (which would
    # otherwise raise a generic ExtensionSecurityError -> 400).
    _, file_extension = os.path.splitext(filename)
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
    incoming_path = save_upload(
        kind=upload_kind,
        upload_dir=core_config.FILES_UPLOAD_INCOMING_DIR,
        filename=storage_key,
    )
    try:
        # Streamed from disk: the file can be up to 200 MiB.
        digest = core_file_uploads.sha256_file(incoming_path) if fingerprint else None
    except Exception:
        # The caller never receives the path, so nothing else would remove it.
        core_file_uploads.remove_files([incoming_path])
        raise
    return ReceivedUpload(incoming_path=incoming_path, storage_key=storage_key, fingerprint=digest)


def store_received_upload(received: ReceivedUpload, storage: platform_providers.StorageProvider) -> str:
    """Hand a received upload to storage and drop the local copy.

    Args:
        received: The upload returned by :func:`receive_upload`.
        storage: The blob-storage provider.

    Returns:
        The storage key the upload was staged under.
    """
    try:
        with open(received.incoming_path, "rb") as handle:
            storage.save_stream(
                UPLOAD_STAGING_STORAGE_AREA,
                upload_staging_storage_key(received.storage_key),
                handle,
            )
    finally:
        core_file_uploads.remove_files([received.incoming_path])
    return received.storage_key


def discard_received_upload(received: ReceivedUpload) -> None:
    """Drop a received upload that will never be stored.

    Args:
        received: The upload returned by :func:`receive_upload`.
    """
    core_file_uploads.remove_files([received.incoming_path])


def process_staged_upload(
    token_user_id: int,
    staged_key: str,
    storage: platform_providers.StorageProvider,
    db: Session,
) -> list[activity_schema.ActivityRead] | None:
    """Decompress, parse and persist a previously staged upload.

    Runs on a background worker, on any node: the bytes come back from the
    storage provider and are materialised into a private temp directory, because
    the parsers work from a path. The staged blob is deliberately left in place:
    the caller removes it with :func:`discard_staged_upload` only after the job's
    outcome is committed, so a crash in between retries against the blob instead
    of finding it gone.

    Args:
        token_user_id: The user the activities belong to.
        staged_key: Key returned by :func:`store_received_upload`.
        storage: The blob-storage provider.
        db: Database session.

    Returns:
        List of created Activity schemas, or None if no activity
        could be parsed from the file.

    Raises:
        InvalidInputError: When the staged blob is gone, or a ``.gz``
            decompresses to an unsupported payload.
        ProcessingError: On an internal failure.
    """
    _, file_extension = os.path.splitext(staged_key)
    # Private directory so the parsed file cannot collide with another job's,
    # and so its removal is unconditional.
    work_dir = tempfile.mkdtemp(prefix="activity-upload-")
    file_path = os.path.join(work_dir, staged_key)
    upload_artifacts: list[str] = [file_path]

    try:
        if not activity_ingestion_staging.copy_blob_to_path(
            UPLOAD_STAGING_STORAGE_AREA, upload_staging_storage_key(staged_key), file_path, storage
        ):
            raise core_exceptions.InvalidInputError("The uploaded file is no longer available")

        if file_extension.lower() == ".gz":
            file_path, file_extension = core_file_uploads.decompress_gzip(file_path)
            # ``decompress_gzip`` returns a new temp file; track it next to the
            # staging .gz so a later failure cleans both up.
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

        created_activities = activity_ingestion_pipeline_service.store_activities_from_file(
            token_user_id,
            file_path,
            file_extension,
            file_base_name,
            db,
            source=activity_ingestion_contracts.UploadSource(),
            storage=storage,
        )
        return created_activities
    except core_exceptions.DomainError:
        # Caught only so the partial artifacts are cleaned up before the error
        # propagates unchanged. The staged blob is deliberately kept:
        # the caller decides whether this failure is terminal or retryable.
        raise
    except (
        OSError,
        EOFError,
        gzip.BadGzipFile,
        shutil.Error,
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


def discard_staged_upload(staged_key: str, storage: platform_providers.StorageProvider) -> None:
    """Remove a staged upload's blob, ignoring failures.

    Called once a job reaches a terminal state so a rejected or imported upload
    does not leave bytes behind. Best-effort: failing to delete the blob must not
    turn a finished import into a failed one.

    Args:
        staged_key: The storage key to remove.
        storage: The blob-storage provider.
    """
    try:
        storage.delete(
            UPLOAD_STAGING_STORAGE_AREA,
            upload_staging_storage_key(staged_key),
        )
    except Exception as err:
        logger.warning(
            "Could not remove a staged upload",
            exc_info=err,
            extra=core_logger.context(storage_key=staged_key),
        )
