"""Centralized file upload handling with security validation.

All file uploads in the backend MUST go through this module:

- :func:`validate_upload` — content-type-aware validation (no write).
- :func:`save_validated_upload` — validate + persist to disk
  (optionally streamed for large files).
- :func:`save_validated_upload_sync` / :func:`validate_local_file_sync` —
  synchronous variants for sync FastAPI routes and threadpool workers.
- :data:`file_validator` — single shared :class:`FileValidator` instance.

The unified pipeline gives every upload the same defenses:

- Filename security (Unicode, Windows reserved names, traversal)
  via :mod:`safeuploads`.
- MIME / magic-number / signature validation per content type.
- Configured size and decompression-bomb limits.
- Atomic ``.part``-then-rename writes with cleanup on failure.
- Structured audit logging with a per-request correlation ID.
"""

import asyncio
import contextlib
import glob
import io
import os
import shutil
import tempfile
import zipfile
from collections.abc import Awaitable, Callable, Coroutine
from enum import StrEnum
from pathlib import Path, PureWindowsPath
from typing import Any

import aiofiles
import aiofiles.os
from fastapi import HTTPException, UploadFile, status
from safeuploads import (
    FileSecurityConfig,
    FileValidator,
    SecurityLimits,
)
from safeuploads.audit import SecurityAuditLogger
from safeuploads.exceptions import (
    CompressionSecurityError,
    ExtensionSecurityError,
    FilenameSecurityError,
    FileProcessingError,
    FileSecurityError,
    FileSignatureError,
    FileSizeError,
    FileValidationError,
    MimeTypeError,
    UnicodeSecurityError,
    WindowsReservedNameError,
    ZipBombError,
)

import core.logger as core_logger

# ---------------------------------------------------------------------------
# Module-level configuration and shared validator
# ---------------------------------------------------------------------------

# Activity files (.gpx/.tcx/.fit) and gzip-wrapped variants can be
# large multi-day .fit files. 200 MiB matches the historical cap
# enforced by the legacy activity-upload helper.
_MAX_ACTIVITY_BYTES = 200 * 1024 * 1024
_MAX_GZIP_BYTES = 200 * 1024 * 1024

# Profile-import ZIPs can contain thousands of activity files. The
# uncompressed/individual entry counts here mirror the previous
# ``profile/router.py`` configuration so behaviour is preserved.
_MAX_ZIP_BYTES = 500 * 1024 * 1024
_MAX_UNCOMPRESSED_BYTES = 2 * 1024 * 1024 * 1024
_MAX_FILES_SAME_TYPE = 2000

# Default 20 MiB image cap from safeuploads is kept; explicitly
# stated here so it appears alongside the other ceilings.
_MAX_IMAGE_BYTES = 20 * 1024 * 1024


def _build_security_config() -> FileSecurityConfig:
    """Build the application-wide :class:`FileSecurityConfig`.

    Returns:
        Configured instance with Endurain-specific limits applied.
    """
    limits = SecurityLimits(
        max_image_size=_MAX_IMAGE_BYTES,
        max_zip_size=_MAX_ZIP_BYTES,
        max_activity_file_size=_MAX_ACTIVITY_BYTES,
        max_gzip_size=_MAX_GZIP_BYTES,
        max_uncompressed_size=_MAX_UNCOMPRESSED_BYTES,
        max_number_files_same_type=_MAX_FILES_SAME_TYPE,
        enable_audit_logging=True,
    )
    config = FileSecurityConfig()
    config.limits = limits
    return config


#: Application-wide :class:`FileValidator`. Stateless w.r.t. uploads;
#: safe to share. Do **not** instantiate ``FileValidator`` elsewhere.
file_validator: FileValidator = FileValidator(config=_build_security_config())

#: Structured audit logger backing the ``safeuploads.audit`` Python
#: logger. Records validation start/success/failure events with a
#: per-request correlation ID.
audit_logger: SecurityAuditLogger = SecurityAuditLogger(enabled=True)


# ---------------------------------------------------------------------------
# Upload kinds and per-kind dispatch
# ---------------------------------------------------------------------------


class UploadKind(StrEnum):
    """Logical content-type of an upload."""

    IMAGE = "image"
    ZIP = "zip"
    ACTIVITY = "activity"
    GZIP = "gzip"


def _validator_for(
    kind: UploadKind,
) -> Callable[[UploadFile], Awaitable[None]]:
    """Return the safeuploads validator coroutine for a kind."""
    if kind is UploadKind.IMAGE:
        return file_validator.validate_image_file
    if kind is UploadKind.ZIP:
        return file_validator.validate_zip_file
    if kind is UploadKind.ACTIVITY:
        return file_validator.validate_activity_file
    if kind is UploadKind.GZIP:
        return file_validator.validate_gzip_file
    raise ValueError(f"Unsupported UploadKind: {kind!r}")


def _max_bytes_for(kind: UploadKind) -> int:
    """Return the configured byte cap for a kind."""
    limits = file_validator.config.limits
    if kind is UploadKind.IMAGE:
        return limits.max_image_size
    if kind is UploadKind.ZIP:
        return limits.max_zip_size
    if kind is UploadKind.ACTIVITY:
        return limits.max_activity_file_size
    if kind is UploadKind.GZIP:
        return limits.max_gzip_size
    raise ValueError(f"Unsupported UploadKind: {kind!r}")


# ---------------------------------------------------------------------------
# Exception mapping
# ---------------------------------------------------------------------------


def _to_http_exception(err: FileSecurityError) -> HTTPException:
    """Translate a safeuploads exception into an HTTPException.

    The error code from :mod:`safeuploads.exceptions` is preserved in
    the ``detail`` payload so clients can react programmatically.

    Args:
        err: Safeuploads exception raised during validation.

    Returns:
        HTTPException with the appropriate status code and a
        machine-readable detail body.
    """
    if isinstance(err, FileSizeError):
        status_code = status.HTTP_413_CONTENT_TOO_LARGE
    elif isinstance(
        err,
        (
            MimeTypeError,
            FileSignatureError,
            ExtensionSecurityError,
            FilenameSecurityError,
            WindowsReservedNameError,
            UnicodeSecurityError,
            ZipBombError,
            CompressionSecurityError,
            FileValidationError,
        ),
    ):
        status_code = status.HTTP_400_BAD_REQUEST
    elif isinstance(err, FileProcessingError):
        status_code = status.HTTP_500_INTERNAL_SERVER_ERROR
    else:
        status_code = status.HTTP_500_INTERNAL_SERVER_ERROR

    detail: dict[str, str] = {"message": str(err)}
    error_code = getattr(err, "error_code", None)
    if error_code is not None:
        detail["code"] = str(error_code)
    return HTTPException(status_code=status_code, detail=detail)


# ---------------------------------------------------------------------------
# Validation-only entry point
# ---------------------------------------------------------------------------


async def validate_upload(file: UploadFile, *, kind: UploadKind) -> None:
    """Validate an upload's content without persisting it to disk.

    Use this when the caller wants to consume the file in memory
    (e.g. ZIP profile-import) but still needs the unified safety
    guarantees.

    Args:
        file: Incoming :class:`fastapi.UploadFile`.
        kind: Logical content type to validate against.

    Raises:
        HTTPException: 400/413/500 mapped from the underlying
            safeuploads exception (see :func:`_to_http_exception`).
    """
    validator = _validator_for(kind)
    try:
        await validator(file)
    except FileSecurityError as err:
        core_logger.print_to_log(
            f"Upload validation failed: kind={kind.value} type={type(err).__name__}",
            "warning",
            exc=err,
        )
        raise _to_http_exception(err) from err


async def validate_local_file(
    path: str | os.PathLike,
    *,
    kind: UploadKind,
    filename: str | None = None,
) -> None:
    """Run :func:`validate_upload` against a file already on disk.

    Wraps the on-disk file in an :class:`UploadFile` so the same
    safeuploads validator can be applied (e.g. after decompressing
    a ``.gz`` activity upload).

    Args:
        path: Filesystem path of the file to validate.
        kind: Logical content type to validate against.
        filename: Optional logical filename used for filename and
            extension checks. Defaults to ``os.path.basename(path)``.

    Raises:
        HTTPException: As :func:`validate_upload`.
    """
    actual_filename = filename or os.path.basename(os.fspath(path))
    # Open in binary mode; UploadFile accepts any binary file object.
    with open(path, "rb") as fh:
        wrapped = UploadFile(file=fh, filename=actual_filename)
        try:
            await validate_upload(wrapped, kind=kind)
        finally:
            await wrapped.close()


# ---------------------------------------------------------------------------
# Synchronous entry points (for sync FastAPI routes + threadpool workers)
# ---------------------------------------------------------------------------


def _run_validator_sync(coro: Coroutine[Any, Any, None]) -> None:
    """Drive an async validator coroutine to completion synchronously.

    The safeuploads validators are async, but sync callers — a synchronous
    FastAPI route (Starlette runs it on a threadpool worker) or the bulk-import
    ``ThreadPoolExecutor`` — have no running event loop. A private loop is created
    for the duration of validation via :func:`asyncio.run`.

    Must **not** be called from the main async thread (``asyncio.run`` refuses to
    run inside an already-running loop); use the ``async`` entry points there.

    Args:
        coro: The validator coroutine to run (e.g. ``validate_upload(...)``).

    Returns:
        None.

    Raises:
        HTTPException: Whatever the wrapped validator raises.
    """
    asyncio.run(coro)


def validate_local_file_sync(
    path: str | os.PathLike,
    *,
    kind: UploadKind,
    filename: str | None = None,
) -> None:
    """Synchronous counterpart of :func:`validate_local_file`.

    Validates a file already on disk (e.g. the inner payload after decompressing a
    ``.gz`` activity) from a synchronous context. Runs the shared safeuploads
    validator to completion on a private event loop.

    Args:
        path: Filesystem path of the file to validate.
        kind: Logical content type to validate against.
        filename: Optional logical filename used for filename and extension
            checks. Defaults to ``os.path.basename(path)``.

    Raises:
        HTTPException: As :func:`validate_upload`.
    """
    actual_filename = filename or os.path.basename(os.fspath(path))
    with open(path, "rb") as fh:
        wrapped = UploadFile(file=fh, filename=actual_filename)
        _run_validator_sync(validate_upload(wrapped, kind=kind))


# ---------------------------------------------------------------------------
# Filename resolver (defense in depth — server-generated names only)
# ---------------------------------------------------------------------------


def _resolve_upload_path(upload_dir: str, filename: str) -> Path:
    """
    Resolve an upload filename inside the target directory.

    Args:
        upload_dir: Trusted upload directory.
        filename: Caller-provided filename.

    Returns:
        Resolved path inside the upload directory.

    Raises:
        HTTPException: If the filename is empty or unsafe.
    """
    candidate_name = Path(filename)
    if not filename or candidate_name.is_absolute():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid filename",
        )
    if candidate_name.name != filename:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid filename",
        )

    if "\x00" in filename:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid filename",
        )

    upload_root = Path(upload_dir).resolve()
    file_path = (upload_root / filename).resolve()
    try:
        file_path.relative_to(upload_root)
    except ValueError as err:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid filename",
        ) from err
    return file_path


def resolve_storage_path(upload_dir: str, filename: str) -> Path:
    """Resolve a server-generated filename inside a storage dir.

    Args:
        upload_dir: Trusted storage directory.
        filename: Server-generated filename to resolve.

    Returns:
        Resolved path inside ``upload_dir``.

    Raises:
        HTTPException: If the filename is empty or unsafe.
    """
    return _resolve_upload_path(upload_dir, filename)


async def save_file(
    file: UploadFile | bytes,
    upload_dir: str,
    filename: str,
) -> str:
    """
    Save uploaded bytes to a validated destination path.

    Internal write primitive used by :func:`save_validated_upload`.
    Callers that need security validation MUST go through the
    :func:`save_validated_upload` entry point so that filename
    sanitization, magic-number, and size checks are applied.

    Args:
        file: Uploaded FastAPI file or raw bytes.
        upload_dir: Trusted upload directory.
        filename: Filename to write within upload_dir.

    Returns:
        Full filesystem path where the file was saved.

    Raises:
        HTTPException: 400 for unsafe names, 500 for write failures.
    """
    file_path: Path | None = None
    try:
        # Ensure upload directory exists
        await aiofiles.os.makedirs(upload_dir, exist_ok=True)

        file_path = _resolve_upload_path(upload_dir, filename)

        # Save file asynchronously
        if isinstance(file, bytes):
            content = file
        else:
            # Defensive: validators leave the cursor at 0, but a
            # caller may have read the stream. Always rewind.
            with contextlib.suppress(Exception):
                await file.seek(0)
            content = await file.read()
        async with aiofiles.open(file_path, "wb") as save_file:
            await save_file.write(content)

        core_logger.print_to_log(
            f"File saved successfully: {file_path}",
            "debug",
        )

        return str(file_path)
    except HTTPException:
        raise
    except Exception as err:
        core_logger.print_to_log(
            f"Error in save_file: {type(err).__name__}",
            "error",
            exc=err,
        )

        # Remove the file if it was created
        if file_path and await aiofiles.os.path.exists(file_path):
            await aiofiles.os.remove(file_path)

        # Raise an HTTPException with a 500 Internal Server Error
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to save file",
        ) from err


# ---------------------------------------------------------------------------
# Streaming writer primitive
# ---------------------------------------------------------------------------

_STREAM_CHUNK_BYTES = 1024 * 1024


def _stream_to_path_sync(file: UploadFile, destination: Path, max_bytes: int) -> None:
    """Stream an UploadFile to ``destination`` in fixed-size chunks.

    Writes to a sibling ``.part`` file first and atomically renames
    on success. Removes the ``.part`` file on any failure path so
    the destination directory never accumulates orphaned bytes.

    Args:
        file: Incoming FastAPI UploadFile (synchronous file object).
        destination: Final path to write to.
        max_bytes: Hard cap on total bytes accepted.

    Raises:
        HTTPException: 413 when the upload exceeds ``max_bytes``.
        OSError: Re-raised after best-effort cleanup of ``.part``.
    """
    part = destination.with_suffix(destination.suffix + ".part")
    bytes_written = 0
    try:
        # The validators leave file.file at offset 0; rewind defensively.
        with contextlib.suppress(Exception):
            file.file.seek(0)
        with open(part, "wb") as out:
            while True:
                chunk = file.file.read(_STREAM_CHUNK_BYTES)
                if not chunk:
                    break
                bytes_written += len(chunk)
                if bytes_written > max_bytes:
                    raise HTTPException(
                        status_code=(status.HTTP_413_CONTENT_TOO_LARGE),
                        detail={
                            "message": ("Uploaded file exceeds maximum allowed size"),
                            "code": "FILE_SIZE_EXCEEDED",
                        },
                    )
                out.write(chunk)
        os.replace(part, destination)
    except BaseException:
        try:
            if part.exists():
                part.unlink()
        except OSError:
            pass
        raise


async def _stream_to_path(file: UploadFile, destination: Path, max_bytes: int) -> None:
    """Async wrapper around :func:`_stream_to_path_sync`.

    Runs the blocking I/O in a worker thread to avoid stalling the
    event loop on large uploads.
    """
    await asyncio.to_thread(_stream_to_path_sync, file, destination, max_bytes)


def _bytes_to_path_sync(data: bytes, destination: Path, max_bytes: int) -> None:
    """Write bytes to ``destination`` via an atomic sibling file.

    Args:
        data: Bytes to persist.
        destination: Final path to write to.
        max_bytes: Hard cap on total bytes accepted.

    Returns:
        None.

    Raises:
        HTTPException: 413 when ``data`` exceeds ``max_bytes``.
        OSError: Re-raised after best-effort cleanup of ``.part``.
    """
    if len(data) > max_bytes:
        raise HTTPException(
            status_code=status.HTTP_413_CONTENT_TOO_LARGE,
            detail={
                "message": "Uploaded file exceeds maximum allowed size",
                "code": "FILE_SIZE_EXCEEDED",
            },
        )

    part = destination.with_suffix(destination.suffix + ".part")
    try:
        with open(part, "wb") as out:
            out.write(data)
        os.replace(part, destination)
    except BaseException:
        try:
            if part.exists():
                part.unlink()
        except OSError:
            pass
        raise


async def _bytes_to_path(data: bytes, destination: Path, max_bytes: int) -> None:
    """Async wrapper around :func:`_bytes_to_path_sync`.

    Args:
        data: Bytes to persist.
        destination: Final path to write to.
        max_bytes: Hard cap on total bytes accepted.

    Returns:
        None.

    Raises:
        HTTPException: As :func:`_bytes_to_path_sync`.
        OSError: As :func:`_bytes_to_path_sync`.
    """
    await asyncio.to_thread(_bytes_to_path_sync, data, destination, max_bytes)


# ---------------------------------------------------------------------------
# Unified validated-write entry point
# ---------------------------------------------------------------------------


async def save_validated_upload(
    file: UploadFile,
    *,
    kind: UploadKind,
    upload_dir: str,
    filename: str,
    stream: bool = False,
) -> str:
    """Validate an upload then persist it to ``upload_dir/filename``.

    This is the single sanctioned entry point for any router that
    needs to write an :class:`UploadFile` to disk.

    Args:
        file: Incoming FastAPI UploadFile.
        kind: Logical content type, drives validator + size cap.
        upload_dir: Trusted destination directory.
        filename: **Server-generated** filename within ``upload_dir``.
            Must not contain path separators; verified by
            :func:`_resolve_upload_path` as defense in depth.
        stream: When True, persist via the streaming writer (used
            for large activity files). When False, the validated
            content is written via :func:`save_file`.

    Returns:
        Absolute filesystem path of the saved file.

    Raises:
        HTTPException: 400/413/500 depending on the failure mode.
    """
    # Validate first; safeuploads rewinds the stream on success.
    await validate_upload(file, kind=kind)

    try:
        await aiofiles.os.makedirs(upload_dir, exist_ok=True)
        destination = _resolve_upload_path(upload_dir, filename)

        if stream:
            await _stream_to_path(file, destination, _max_bytes_for(kind))
            saved_path = str(destination)
        else:
            saved_path = await save_file(file, upload_dir, filename)

        return saved_path
    except HTTPException:
        raise
    except Exception as err:
        core_logger.print_to_log(
            f"Error in save_validated_upload: {type(err).__name__}",
            "error",
            exc=err,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "message": "Failed to save file",
                "code": "FILE_SAVE_FAILED",
            },
        ) from err


def save_validated_upload_sync(
    file: UploadFile,
    *,
    kind: UploadKind,
    upload_dir: str,
    filename: str,
) -> str:
    """Synchronous counterpart of :func:`save_validated_upload`.

    For synchronous FastAPI routes (Starlette runs them on a threadpool worker)
    and other sync contexts. Validates the upload with the shared safeuploads
    validator, then streams it to ``upload_dir/filename`` with the synchronous
    streaming writer (``.part``-then-rename, size-capped) — the same defenses as
    the async path, without touching the event loop.

    Content validation runs on a private event loop (:func:`_run_validator_sync`),
    so this must be called from a thread with **no** running loop. Use
    :func:`save_validated_upload` from async code.

    Args:
        file: Incoming FastAPI UploadFile.
        kind: Logical content type, drives validator + size cap.
        upload_dir: Trusted destination directory.
        filename: **Server-generated** filename within ``upload_dir``. Must not
            contain path separators; verified by :func:`_resolve_upload_path`.

    Returns:
        Absolute filesystem path of the saved file.

    Raises:
        HTTPException: 400/413/500 depending on the failure mode.
    """
    # Validate first; safeuploads rewinds the stream on success.
    _run_validator_sync(validate_upload(file, kind=kind))

    try:
        os.makedirs(upload_dir, exist_ok=True)
        destination = _resolve_upload_path(upload_dir, filename)
        _stream_to_path_sync(file, destination, _max_bytes_for(kind))
        return str(destination)
    except HTTPException:
        raise
    except Exception as err:
        core_logger.print_to_log(
            f"Error in save_validated_upload_sync: {type(err).__name__}",
            "error",
            exc=err,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "message": "Failed to save file",
                "code": "FILE_SAVE_FAILED",
            },
        ) from err


# ---------------------------------------------------------------------------
# Filesystem cleanup helpers
# ---------------------------------------------------------------------------


async def delete_files_by_pattern(directory: str, pattern: str) -> None:
    """
    Delete files from filesystem matching a glob pattern asynchronously.

    Searches directory for files matching the pattern and removes
    them asynchronously. Silently skips files that no longer exist.

    Args:
        directory: Directory path to search in.
        pattern: Glob pattern to match (e.g., "user_123.*").

    Returns:
        None

    Raises:
        None - errors logged but not raised for resilience.
    """
    try:
        # Build full pattern path
        full_pattern = os.path.join(directory, pattern)

        # Find all files matching the pattern
        files_to_delete = glob.glob(full_pattern)

        # Remove each file found asynchronously
        for file_path in files_to_delete:
            try:
                if await aiofiles.os.path.exists(file_path):
                    await aiofiles.os.remove(file_path)

                core_logger.print_to_log(f"File deleted successfully: {file_path}", "debug")
            except OSError as err:
                core_logger.print_to_log(
                    f"Failed to delete file {file_path}: {err}",
                    "warning",
                    exc=err,
                )
    except Exception as err:
        core_logger.print_to_log(
            f"Error deleting files matching pattern {pattern}: {err}",
            "error",
            exc=err,
        )


# ---------------------------------------------------------------------------
# In-memory bytes validation and persistence
# ---------------------------------------------------------------------------


async def validate_bytes(
    data: bytes,
    *,
    kind: UploadKind,
    filename: str,
) -> None:
    """Validate raw bytes as if they were an :class:`UploadFile`.

    Used for server-side ingestion paths where the bytes did not
    arrive via multipart upload (e.g. Garmin Connect download).

    Args:
        data: Raw byte payload to validate.
        kind: Logical content type to validate against.
        filename: Logical filename used for filename and extension
            checks. Server-generated names only.

    Raises:
        HTTPException: 400/413/500 mapped from safeuploads.
    """
    wrapped = UploadFile(file=io.BytesIO(data), filename=filename)
    try:
        await validate_upload(wrapped, kind=kind)
    finally:
        await wrapped.close()


async def save_validated_bytes(
    data: bytes,
    *,
    kind: UploadKind,
    upload_dir: str,
    filename: str,
) -> str:
    """Validate raw bytes then persist them to ``upload_dir/filename``.

    Equivalent of :func:`save_validated_upload` for byte payloads
    obtained outside the multipart pipeline (Garmin downloads,
    test fixtures, migrations).

    Args:
        data: Raw byte payload.
        kind: Logical content type.
        upload_dir: Trusted destination directory.
        filename: **Server-generated** filename within ``upload_dir``.

    Returns:
        Absolute filesystem path of the saved file.

    Raises:
        HTTPException: 400/413/500 depending on failure mode.
    """
    await validate_bytes(data, kind=kind, filename=filename)
    try:
        await aiofiles.os.makedirs(upload_dir, exist_ok=True)
        destination = _resolve_upload_path(upload_dir, filename)
        await _bytes_to_path(data, destination, _max_bytes_for(kind))
        return str(destination)
    except HTTPException:
        raise
    except Exception as err:
        core_logger.print_to_log(
            f"save_validated_bytes failed: {type(err).__name__}",
            "error",
            exc=err,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "message": "Failed to save file",
                "code": "FILE_SAVE_FAILED",
            },
        ) from err


# ---------------------------------------------------------------------------
# Zip-slip-safe extraction
# ---------------------------------------------------------------------------

# Per-entry safety caps for extract_validated_zip. These mirror the
# safeuploads SecurityLimits but apply during *consumer* iteration so
# that a malformed entry cannot exceed limits even after the archive
# itself passed validation.
_MAX_EXTRACTED_ENTRY_BYTES = _MAX_ACTIVITY_BYTES
_MAX_TOTAL_EXTRACTED_BYTES = _MAX_UNCOMPRESSED_BYTES


def _is_safe_extraction_target(entry_name: str, dest_dir: Path) -> Path | None:
    """Resolve a ZIP entry against ``dest_dir`` and reject escapes.

    Args:
        entry_name: Raw entry name from :meth:`zipfile.ZipFile.namelist`.
        dest_dir: Resolved destination directory.

    Returns:
        Resolved absolute path strictly under ``dest_dir`` or
        ``None`` if the entry is unsafe (absolute, traversal,
        symlink, or escapes the destination).
    """
    # Reject absolute paths and Windows drive prefixes outright.
    candidate = entry_name.replace("\\", "/")
    if not candidate or candidate.startswith("/"):
        return None
    windows_path = PureWindowsPath(candidate)
    if windows_path.is_absolute() or windows_path.drive:
        return None
    # Reject NUL and Windows-reserved characters.
    if "\x00" in candidate:
        return None
    target = (dest_dir / candidate).resolve()
    try:
        target.relative_to(dest_dir)
    except ValueError:
        return None
    if target == dest_dir:
        return None
    return target


def _extract_validated_zip_sync(
    zip_path: Path,
    dest_dir: Path,
    max_entries: int | None,
) -> tuple[Path, list[tuple[Path, Path]]]:
    """Synchronous core of :func:`extract_validated_zip`.

    Performs zip-slip-safe extraction into a private staging dir with
    per-entry and total-size enforcement. Skips directory entries;
    rejects symlinks; refuses duplicate and existing targets.
    """
    extracted: list[tuple[Path, Path]] = []
    seen_targets: set[Path] = set()
    staging_dir: Path | None = None
    total_bytes = 0
    dest_resolved = dest_dir.resolve()
    request_too_large = status.HTTP_413_CONTENT_TOO_LARGE

    try:
        with zipfile.ZipFile(zip_path, "r") as zip_ref:
            members = zip_ref.infolist()
            if max_entries is not None and len(members) > max_entries:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail={
                        "message": (f"Archive contains {len(members)} entries; maximum allowed is {max_entries}"),
                        "code": "ZIP_ENTRY_COUNT_EXCEEDED",
                    },
                )

            staging_dir = Path(
                tempfile.mkdtemp(
                    prefix=".extract-",
                    dir=dest_resolved,
                )
            ).resolve()

            for member in members:
                # Skip directory entries; they are recreated implicitly.
                if member.is_dir():
                    continue

                # Reject symlinks (high bits of external_attr indicate
                # the file mode on Unix; 0xA000 = symlink).
                mode = (member.external_attr >> 16) & 0xFFFF
                if mode and (mode & 0o170000) == 0o120000:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail={
                            "message": (f"Archive contains symlink entry: {member.filename!r}"),
                            "code": "ZIP_SYMLINK_REJECTED",
                        },
                    )

                target = _is_safe_extraction_target(member.filename, dest_resolved)
                if target is None:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail={
                            "message": (f"Archive entry escapes destination: {member.filename!r}"),
                            "code": "ZIP_SLIP_REJECTED",
                        },
                    )

                if target in seen_targets:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail={
                            "message": (f"Archive contains duplicate target: {member.filename!r}"),
                            "code": "ZIP_DUPLICATE_TARGET",
                        },
                    )
                if target.exists():
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail={
                            "message": (f"Archive target already exists: {member.filename!r}"),
                            "code": "ZIP_TARGET_EXISTS",
                        },
                    )
                seen_targets.add(target)

                # Per-entry uncompressed size guard (declared size).
                if member.file_size > _MAX_EXTRACTED_ENTRY_BYTES:
                    raise HTTPException(
                        status_code=request_too_large,
                        detail={
                            "message": ("Archive entry exceeds maximum entry size"),
                            "code": "ZIP_ENTRY_SIZE_EXCEEDED",
                        },
                    )
                total_bytes += member.file_size
                if total_bytes > _MAX_TOTAL_EXTRACTED_BYTES:
                    raise HTTPException(
                        status_code=request_too_large,
                        detail={
                            "message": ("Archive total uncompressed size exceeds maximum"),
                            "code": "ZIP_TOTAL_SIZE_EXCEEDED",
                        },
                    )

                staged_target = staging_dir / target.relative_to(dest_resolved)
                staged_target.parent.mkdir(parents=True, exist_ok=True)
                try:
                    with zip_ref.open(member, "r") as src, open(staged_target, "xb") as dst:
                        # Stream copy with a hard cap so a lying
                        # file_size in the central directory cannot
                        # fill the disk.
                        written = 0
                        while True:
                            chunk = src.read(_STREAM_CHUNK_BYTES)
                            if not chunk:
                                break
                            written += len(chunk)
                            if written > _MAX_EXTRACTED_ENTRY_BYTES:
                                raise HTTPException(
                                    status_code=request_too_large,
                                    detail={
                                        "message": ("Archive entry exceeds maximum entry size"),
                                        "code": ("ZIP_ENTRY_SIZE_EXCEEDED"),
                                    },
                                )
                            dst.write(chunk)
                except BaseException:
                    with contextlib.suppress(OSError):
                        staged_target.unlink(missing_ok=True)
                    raise
                extracted.append((staged_target, target))
    except BaseException:
        if staging_dir is not None:
            shutil.rmtree(staging_dir, ignore_errors=True)
        raise

    if staging_dir is None:
        staging_dir = Path(tempfile.mkdtemp(prefix=".extract-", dir=dest_resolved)).resolve()
    return staging_dir, extracted


def _promote_extracted_files_sync(
    extracted: list[tuple[Path, Path]],
    dest_dir: Path,
) -> list[Path]:
    """Move staged files into ``dest_dir`` without overwriting.

    Args:
        extracted: Pairs of staged file path and final destination.
        dest_dir: Resolved destination directory.

    Returns:
        Final paths promoted into ``dest_dir``.

    Raises:
        HTTPException: 400 when a final target is unsafe or exists.
        OSError: Re-raised for filesystem failures.
    """
    final_paths: list[Path] = []
    created_dirs: list[Path] = []

    try:
        for staged_path, final_path in extracted:
            parent_resolved = final_path.parent.resolve()
            try:
                parent_resolved.relative_to(dest_dir)
            except ValueError as err:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail={
                        "message": "Archive entry escapes destination",
                        "code": "ZIP_SLIP_REJECTED",
                    },
                ) from err

            # Track every directory level we create, not just the
            # leaf, so rollback removes intermediate dirs too
            # (`mkdir(parents=True)` may have created several).
            missing_ancestors: list[Path] = []
            probe = parent_resolved
            while not probe.exists() and probe != dest_dir:
                missing_ancestors.append(probe)
                probe = probe.parent
            parent_resolved.mkdir(parents=True, exist_ok=True)
            # Deepest-first so rmdir succeeds during reverse cleanup.
            created_dirs.extend(missing_ancestors)

            final_resolved = (parent_resolved / final_path.name).resolve()
            try:
                final_resolved.relative_to(dest_dir)
            except ValueError as err:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail={
                        "message": "Archive entry escapes destination",
                        "code": "ZIP_SLIP_REJECTED",
                    },
                ) from err

            if final_resolved.exists():
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail={
                        "message": "Archive target already exists",
                        "code": "ZIP_TARGET_EXISTS",
                    },
                )

            try:
                # ``os.link`` is atomic but requires the staging dir
                # and ``dest_dir`` to live on the same filesystem. We
                # guarantee this by creating ``staging_dir`` via
                # ``tempfile.mkdtemp(dir=dest_resolved)`` in
                # :func:`_extract_validated_zip_sync`. Do not relocate
                # the staging dir without revisiting this contract.
                os.link(staged_path, final_resolved)
            except FileExistsError as err:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail={
                        "message": "Archive target already exists",
                        "code": "ZIP_TARGET_EXISTS",
                    },
                ) from err
            staged_path.unlink()
            final_paths.append(final_resolved)
    except BaseException:
        for path in reversed(final_paths):
            with contextlib.suppress(OSError):
                path.unlink(missing_ok=True)
        # ``created_dirs`` is already deepest-first within each
        # ancestor chain (see ``missing_ancestors`` build above), so
        # iterate in natural order to ensure children are removed
        # before their parents during rollback.
        for created in created_dirs:
            with contextlib.suppress(OSError):
                created.rmdir()
        raise

    return final_paths


async def extract_validated_zip(
    zip_path: str | os.PathLike,
    *,
    dest_dir: str | os.PathLike,
    per_entry_kind: UploadKind | None = None,
    max_entries: int | None = None,
) -> list[Path]:
    """Extract ``zip_path`` into ``dest_dir`` with zip-slip safety.

    The ZIP archive itself MUST already have been validated via
    :func:`validate_local_file` (or arrived through
    :func:`save_validated_upload`) — this helper enforces *consumer*
    safety during iteration.

    Args:
        zip_path: Path of the ZIP archive to extract.
        dest_dir: Destination directory; created if missing.
        per_entry_kind: When provided, every extracted entry is
            re-validated via :func:`validate_local_file` against the
            given :class:`UploadKind` and removed if invalid.
        max_entries: Hard cap on number of entries; defaults to the
            module-wide ``_MAX_FILES_SAME_TYPE`` if not specified.

    Returns:
        List of extracted file paths under ``dest_dir``.

    Raises:
        HTTPException: 400 for zip-slip / symlink / unsafe entries,
            413 for size-cap violations, 500 for I/O failures.
    """
    if max_entries is None:
        max_entries = _MAX_FILES_SAME_TYPE
    dest_path = Path(os.fspath(dest_dir))
    await aiofiles.os.makedirs(dest_path, exist_ok=True)

    staging_dir: Path | None = None
    try:
        staging_dir, extracted = await asyncio.to_thread(
            _extract_validated_zip_sync,
            Path(os.fspath(zip_path)),
            dest_path,
            max_entries,
        )
    except HTTPException:
        raise
    except (zipfile.BadZipFile, OSError) as err:
        core_logger.print_to_log(
            f"extract_validated_zip failed: {type(err).__name__}",
            "error",
            exc=err,
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "message": "Failed to extract archive",
                "code": "ZIP_EXTRACTION_FAILED",
            },
        ) from err

    try:
        if per_entry_kind is not None:
            kept: list[tuple[Path, Path]] = []
            for staged_entry, final_entry in extracted:
                try:
                    await validate_local_file(
                        staged_entry,
                        kind=per_entry_kind,
                        filename=final_entry.name,
                    )
                except HTTPException:
                    with contextlib.suppress(OSError):
                        staged_entry.unlink(missing_ok=True)
                    core_logger.print_to_log(
                        f"extract_validated_zip dropped invalid entry: {final_entry.name}",
                        "warning",
                    )
                    continue
                kept.append((staged_entry, final_entry))
            extracted = kept

        try:
            return await asyncio.to_thread(
                _promote_extracted_files_sync,
                extracted,
                dest_path.resolve(),
            )
        except HTTPException:
            raise
        except OSError as err:
            core_logger.print_to_log(
                f"extract_validated_zip promotion failed: {type(err).__name__}",
                "error",
                exc=err,
            )
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail={
                    "message": "Failed to promote extracted files",
                    "code": "ZIP_PROMOTION_FAILED",
                },
            ) from err
    finally:
        if staging_dir is not None:
            await asyncio.to_thread(shutil.rmtree, staging_dir, ignore_errors=True)


# ---------------------------------------------------------------------------
# Path-bounded filesystem helpers
# ---------------------------------------------------------------------------


def _resolve_within(path: str | os.PathLike, base_dir: Path) -> Path:
    """Resolve ``path`` and verify it stays under ``base_dir``.

    Symlinks are followed via ``Path.resolve``; the resolved target
    must be strictly inside ``base_dir``.

    Args:
        path: Filesystem path to verify.
        base_dir: Trusted base directory (already resolved).

    Returns:
        Resolved :class:`Path`.

    Raises:
        HTTPException: 400 when the resolved path escapes ``base_dir``.
    """
    resolved = Path(os.fspath(path)).resolve()
    try:
        resolved.relative_to(base_dir)
    except ValueError as err:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "message": "Path escapes the allowed directory",
                "code": "PATH_OUTSIDE_BASE_DIR",
            },
        ) from err
    return resolved


def move_within(
    src: str | os.PathLike,
    dest_dir: str | os.PathLike,
    *,
    filename: str,
    src_base_dir: str | os.PathLike | None = None,
    overwrite: bool = False,
) -> Path:
    """Move ``src`` into ``dest_dir`` as ``filename`` safely.

    Replacement for the legacy ``move_file`` helper. The final
    destination is always constrained to ``dest_dir``. When
    ``src_base_dir`` is provided, the source path is also required
    to resolve under that trusted directory before the move.

    Args:
        src: Source path to move.
        dest_dir: Trusted destination directory; created if missing.
        filename: **Server-generated** filename within ``dest_dir``.
            Validated via :func:`_resolve_upload_path`.
        src_base_dir: Optional trusted source directory. When set,
            ``src`` must resolve under it.
        overwrite: When ``False`` (default) an existing destination
            file aborts the move with HTTP 400 — mirrors the
            no-overwrite contract of :func:`extract_validated_zip`.
            Callers that intentionally need to replace an existing
            file must opt in explicitly.

    Returns:
        Resolved destination :class:`Path`.

    Raises:
        HTTPException: 400 for unsafe filename / containment
            violations or pre-existing destination, 500 for I/O
            failures.
    """
    dest_dir_str = os.fspath(dest_dir)
    try:
        os.makedirs(dest_dir_str, exist_ok=True)
        destination = _resolve_upload_path(dest_dir_str, filename)
        if not overwrite and destination.exists():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={
                    "message": "Destination file already exists",
                    "code": "FILE_DESTINATION_EXISTS",
                },
            )
        source = Path(os.fspath(src)).resolve()
        if src_base_dir is not None:
            source = _resolve_within(source, Path(os.fspath(src_base_dir)).resolve())
        shutil.move(source, destination)
        return destination
    except HTTPException:
        raise
    except (OSError, shutil.Error) as err:
        core_logger.print_to_log(
            f"move_within failed: {type(err).__name__}",
            "error",
            exc=err,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "message": "Failed to move file",
                "code": "FILE_MOVE_FAILED",
            },
        ) from err


def safe_remove_within(
    path: str | os.PathLike,
    *,
    base_dir: str | os.PathLike,
) -> bool:
    """Remove ``path`` only if it resolves under ``base_dir``.

    Best-effort: missing files are treated as success. Any path
    that escapes ``base_dir`` is rejected before any I/O.

    Args:
        path: File to remove.
        base_dir: Trusted directory the file must live under.

    Returns:
        ``True`` if a file was removed, ``False`` if it did not
        exist.

    Raises:
        HTTPException: 400 when ``path`` escapes ``base_dir``.
    """
    base_resolved = Path(os.fspath(base_dir)).resolve()
    target = _resolve_within(path, base_resolved)
    try:
        if target.is_file():
            target.unlink()
            return True
        return False
    except FileNotFoundError:
        return False
    except OSError as err:
        core_logger.print_to_log(
            f"safe_remove_within failed for {target.name}: {type(err).__name__}",
            "warning",
            exc=err,
        )
        return False
