"""Centralized file upload handling with security validation.

All file uploads in the backend MUST go through this module:

- :func:`read_validated_upload_sync` / :func:`save_validated_upload_sync` —
  validate an upload, then return its bytes or stream it to disk.
- :func:`validate_bytes_sync` / :func:`save_validated_bytes_sync` /
  :func:`validate_local_file_sync` — the same for bytes and files on disk.
- :func:`extract_validated_zip_sync` — zip-slip-safe extraction.
- :data:`file_validator` — single shared :class:`FileValidator` instance.

Every entry point blocks: the safeuploads synchronous validators refuse a
thread that runs an event loop, so they are called from synchronous FastAPI
routes (Starlette runs them on a threadpool worker), jobs and worker pools.

The unified pipeline gives every upload the same defenses:

- Filename security (Unicode, Windows reserved names, traversal)
  via :mod:`safeuploads`.
- MIME / magic-number / signature validation per content type.
- Configured size and decompression-bomb limits.
- Atomic ``.part``-then-rename writes with cleanup on failure.
- Structured audit logging with a per-request correlation ID.
"""

import contextlib
import gzip
import hashlib
import io
import os
import shutil
import tempfile
import zipfile
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path, PurePosixPath, PureWindowsPath
from types import MappingProxyType
from typing import BinaryIO

from fastapi import UploadFile
from PIL import Image, ImageOps, UnidentifiedImageError
from safeuploads import (
    ErrorCode,
    FileSecurityConfig,
    FileValidator,
    SecurityLimits,
    SeekableFile,
    ValidationResult,
)
from safeuploads.exceptions import (
    CompressionSecurityError,
    ExtensionSecurityError,
    FilenameSecurityError,
    FileSecurityError,
    FileSignatureError,
    FileSizeError,
    FileValidationError,
    ImageDimensionError,
    MimeTypeError,
    UnicodeSecurityError,
    WindowsReservedNameError,
    ZipBombError,
)

import core.exceptions as core_exceptions
import core.logger as core_logger

logger = core_logger.get_logger(__name__)

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

# A compressed image can be tiny on disk and still decode to gigabytes, so the byte cap is not enough.
_MAX_IMAGE_PIXELS = 100_000_000


#: The one image allow-list: every accepted extension with the media type it is stored and served as. The upload
#: validator, the route-level extension checks, the content-type maps and the signature sniffing all derive from it.
IMAGE_CONTENT_TYPES: Mapping[str, str] = MappingProxyType(
    {
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".png": "image/png",
        ".webp": "image/webp",
    }
)


def _is_webp(data: bytes) -> bool:
    """Return whether the bytes start with a WebP RIFF container header.

    Args:
        data: The leading bytes of a file.

    Returns:
        True when the header is ``RIFF....WEBP``.
    """
    return data[:4] == b"RIFF" and data[8:12] == b"WEBP"


def _build_security_config() -> FileSecurityConfig:
    """Build the application-wide :class:`FileSecurityConfig`.

    Returns:
        Configured instance with Endurain-specific limits applied.
    """
    limits = SecurityLimits(
        max_image_size=_MAX_IMAGE_BYTES,
        max_image_pixels=_MAX_IMAGE_PIXELS,
        max_zip_size=_MAX_ZIP_BYTES,
        max_activity_file_size=_MAX_ACTIVITY_BYTES,
        max_gzip_size=_MAX_GZIP_BYTES,
        max_uncompressed_size=_MAX_UNCOMPRESSED_BYTES,
        max_number_files_same_type=_MAX_FILES_SAME_TYPE,
        # Strava bulk exports store activities as ``.fit.gz`` entries inside the ZIP.
        allow_nested_archives=True,
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
) -> Callable[[SeekableFile, str], ValidationResult]:
    """Return the safeuploads synchronous validator for a kind."""
    if kind is UploadKind.IMAGE:
        return file_validator.validate_image_file_sync
    if kind is UploadKind.ZIP:
        return file_validator.validate_zip_file_sync
    if kind is UploadKind.ACTIVITY:
        return file_validator.validate_activity_file_sync
    if kind is UploadKind.GZIP:
        return file_validator.validate_gzip_file_sync
    raise ValueError(f"Unsupported UploadKind: {kind!r}")


def max_bytes_for(kind: UploadKind) -> int:
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


def _to_domain_error(err: FileSecurityError) -> core_exceptions.DomainError:
    """Translate a safeuploads exception into a domain error.

    The safeuploads error code is not part of the response: the validators'
    own taxonomy is an implementation detail of this module, and the
    exception is logged with its type by the caller.

    Args:
        err: Safeuploads exception raised during validation.

    Returns:
        ``PayloadTooLargeError`` for a size violation,
        ``UnsupportedMediaTypeError`` for a file type the validators refuse,
        ``InvalidInputError`` for an empty file or other content the validators
        reject, ``ProcessingError`` otherwise.
    """
    if isinstance(err, FileSizeError) and err.error_code == ErrorCode.FILE_EMPTY:
        return core_exceptions.InvalidInputError(str(err))
    if isinstance(err, (FileSizeError, ImageDimensionError)):
        return core_exceptions.PayloadTooLargeError(str(err))
    if isinstance(err, (MimeTypeError, FileSignatureError, ExtensionSecurityError)):
        return core_exceptions.UnsupportedMediaTypeError(str(err))
    if isinstance(
        err,
        (
            FilenameSecurityError,
            WindowsReservedNameError,
            UnicodeSecurityError,
            ZipBombError,
            CompressionSecurityError,
            FileValidationError,
        ),
    ):
        return core_exceptions.InvalidInputError(str(err))
    return core_exceptions.ProcessingError(str(err))


# ---------------------------------------------------------------------------
# Validation-only entry point
# ---------------------------------------------------------------------------


def _validate_file(file: BinaryIO, filename: str, *, kind: UploadKind) -> str:
    """Validate a seekable binary file's content on the calling thread.

    The file is rewound to position 0 on success.

    Args:
        file: The content to validate.
        filename: Logical filename used for filename and extension checks.
        kind: Logical content type to validate against.

    Returns:
        The sanitized filename.

    Raises:
        DomainError: 400/413/415/500 mapped from the underlying
            safeuploads exception (see :func:`_to_domain_error`).
    """
    try:
        return _validator_for(kind)(file, filename).filename
    except FileSecurityError as err:
        logger.warning("Upload validation failed", exc_info=err, extra=core_logger.context(kind=kind.value))
        raise _to_domain_error(err) from err


def _validate_upload(file: UploadFile, *, kind: UploadKind) -> None:
    """Validate an upload and replace its filename with the sanitized one.

    Args:
        file: Incoming :class:`fastapi.UploadFile`.
        kind: Logical content type to validate against.

    Raises:
        DomainError: As :func:`_validate_file`.
    """
    file.filename = _validate_file(file.file, file.filename or "", kind=kind)


def validate_local_file_sync(
    path: str | os.PathLike[str],
    *,
    kind: UploadKind,
    filename: str | None = None,
) -> None:
    """Validate a file already on disk.

    Used for content that did not arrive as an upload, such as the inner payload
    after decompressing a ``.gz`` activity.

    Args:
        path: Filesystem path of the file to validate.
        kind: Logical content type to validate against.
        filename: Optional logical filename used for filename and extension
            checks. Defaults to ``os.path.basename(path)``.

    Raises:
        DomainError: As :func:`_validate_file`.
    """
    actual_filename = filename or os.path.basename(os.fspath(path))
    with open(path, "rb") as fh:
        _validate_file(fh, actual_filename, kind=kind)


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
        DomainError: If the filename is empty or unsafe.
    """
    candidate_name = Path(filename)
    if not filename or candidate_name.is_absolute():
        raise core_exceptions.InvalidInputError("Invalid filename")
    if candidate_name.name != filename:
        raise core_exceptions.InvalidInputError("Invalid filename")

    if "\x00" in filename:
        raise core_exceptions.InvalidInputError("Invalid filename")

    upload_root = Path(upload_dir).resolve()
    file_path = (upload_root / filename).resolve()
    try:
        file_path.relative_to(upload_root)
    except ValueError as err:
        raise core_exceptions.InvalidInputError("Invalid filename") from err
    return file_path


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
        DomainError: 413 when the upload exceeds ``max_bytes``.
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
                    raise core_exceptions.PayloadTooLargeError("Uploaded file exceeds maximum allowed size")
                out.write(chunk)
        os.replace(part, destination)
    except BaseException:
        try:
            if part.exists():
                part.unlink()
        except OSError:
            pass
        raise


def _bytes_to_path_sync(data: bytes, destination: Path, max_bytes: int) -> None:
    """Write bytes to ``destination`` via an atomic sibling file.

    Args:
        data: Bytes to persist.
        destination: Final path to write to.
        max_bytes: Hard cap on total bytes accepted.

    Returns:
        None.

    Raises:
        DomainError: 413 when ``data`` exceeds ``max_bytes``.
        OSError: Re-raised after best-effort cleanup of ``.part``.
    """
    if len(data) > max_bytes:
        raise core_exceptions.PayloadTooLargeError("Uploaded file exceeds maximum allowed size")

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


# ---------------------------------------------------------------------------
# Unified validated-write entry point
# ---------------------------------------------------------------------------


def _read_capped_sync(file: UploadFile, max_bytes: int) -> bytes:
    """Read an already-validated upload into memory, enforcing the size cap."""
    chunks: list[bytes] = []
    total = 0
    # The validators leave file.file at offset 0; rewind defensively.
    with contextlib.suppress(Exception):
        file.file.seek(0)
    while True:
        chunk = file.file.read(_STREAM_CHUNK_BYTES)
        if not chunk:
            break
        total += len(chunk)
        if total > max_bytes:
            raise core_exceptions.PayloadTooLargeError("Uploaded file exceeds maximum allowed size")
        chunks.append(chunk)
    return b"".join(chunks)


def save_validated_upload_sync(
    file: UploadFile,
    *,
    kind: UploadKind,
    upload_dir: str,
    filename: str,
) -> str:
    """Validate an upload then stream it to ``upload_dir/filename``.

    This is the single sanctioned entry point for any route that needs to write
    an :class:`UploadFile` to disk. The write goes through a ``.part`` file that
    is renamed on success and is capped at the kind's size limit.

    Args:
        file: Incoming FastAPI UploadFile.
        kind: Logical content type, drives validator + size cap.
        upload_dir: Trusted destination directory.
        filename: **Server-generated** filename within ``upload_dir``. Must not
            contain path separators; verified by :func:`_resolve_upload_path`.

    Returns:
        Absolute filesystem path of the saved file.

    Raises:
        DomainError: 400/413/415/500 depending on the failure mode.
    """
    # Validate first; safeuploads rewinds the stream on success.
    _validate_upload(file, kind=kind)

    try:
        os.makedirs(upload_dir, exist_ok=True)
        destination = _resolve_upload_path(upload_dir, filename)
        _stream_to_path_sync(file, destination, max_bytes_for(kind))
        return str(destination)
    except core_exceptions.DomainError:
        raise
    except Exception as err:
        logger.debug("Error in save_validated_upload_sync", exc_info=err)
        raise core_exceptions.ProcessingError("Failed to save file") from err


def read_validated_upload_sync(file: UploadFile, *, kind: UploadKind) -> bytes:
    """Validate an upload and return its bytes, without touching the filesystem.

    The read counterpart of :func:`save_validated_upload_sync`, for callers that
    hand the bytes to the platform ``StorageProvider`` (which may be object
    storage) rather than writing them to a local directory. The same safeuploads
    validator and size cap apply, so the only thing that differs is the
    destination.

    Args:
        file: Incoming FastAPI UploadFile.
        kind: Logical content type, drives validator + size cap.

    Returns:
        The validated file contents.

    Raises:
        DomainError: 400/413/415/500 depending on the failure mode.
    """
    _validate_upload(file, kind=kind)

    return _read_capped_sync(file, max_bytes_for(kind))


#: Magic-number prefixes of the image formats the upload validator accepts, with their media type.
_IMAGE_SIGNATURES: tuple[tuple[bytes, str], ...] = (
    (b"\x89PNG\r\n\x1a\n", "image/png"),
    (b"\xff\xd8\xff", "image/jpeg"),
)


def sniff_image_type(data: bytes) -> str | None:
    """Return the media type of image bytes from their magic number.

    Args:
        data: The image bytes.

    Returns:
        The media type, or None when the format is not recognised.
    """
    for signature, media_type in _IMAGE_SIGNATURES:
        if data.startswith(signature):
            return media_type
    if _is_webp(data):
        return "image/webp"
    return None


#: Image formats :func:`strip_image_metadata` can rewrite, with the options each encoder is given.
_REWRITABLE_IMAGE_FORMATS: dict[str, dict[str, int]] = {
    "JPEG": {"quality": 90},
    "PNG": {},
    "WEBP": {"quality": 90},
}


def strip_image_metadata(data: bytes, *, max_dimension: int | None = None) -> bytes:
    """Re-encode an image without its metadata.

    EXIF (including GPS), XMP, PNG text chunks and comments are dropped; the ICC colour profile and PNG
    transparency are kept. The EXIF orientation is applied to the pixels first, so the picture stays upright
    without the tag. The image keeps its format, since callers derive the stored content type from it.

    Args:
        data: The image bytes, already accepted by the byte-level validator.
        max_dimension: When set, the longest edge is reduced to at most this many pixels, keeping the aspect
            ratio. An image already within it is never upscaled.

    Returns:
        The re-encoded image bytes.

    Raises:
        UnsupportedMediaTypeError: When the image is not a JPEG, PNG or WebP.
        InvalidInputError: When the bytes cannot be decoded as an image.
        PayloadTooLargeError: When the image would decode to more than the pixel cap.
    """
    try:
        with Image.open(io.BytesIO(data)) as source:
            image_format = source.format
            if image_format not in _REWRITABLE_IMAGE_FORMATS:
                raise core_exceptions.UnsupportedMediaTypeError("The image must be a JPEG, PNG or WebP file")
            if source.width * source.height > _MAX_IMAGE_PIXELS:
                raise core_exceptions.PayloadTooLargeError("Image dimensions are too large")
            icc_profile = source.info.get("icc_profile")
            transposed = ImageOps.exif_transpose(source)
            # The transposed copy owns its pixels, so it outlives the closed source file.
            image = transposed if transposed is not None else source.copy()
            image.load()
    except Image.DecompressionBombError as err:
        raise core_exceptions.PayloadTooLargeError("Image dimensions are too large") from err
    except (UnidentifiedImageError, OSError, ValueError, SyntaxError) as err:
        raise core_exceptions.InvalidInputError("The image could not be read") from err

    if max_dimension is not None:
        image.thumbnail((max_dimension, max_dimension))
    # Only what is named here is written: the decoded metadata in ``info`` never reaches the encoder.
    options: dict[str, object] = dict(_REWRITABLE_IMAGE_FORMATS[image_format])
    if icc_profile:
        options["icc_profile"] = icc_profile
    if "transparency" in image.info:
        options["transparency"] = image.info["transparency"]
    image.info = {}
    output = io.BytesIO()
    image.save(output, format=image_format, **options)
    return output.getvalue()


# ---------------------------------------------------------------------------
# Filesystem cleanup helpers
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# In-memory bytes validation and persistence
# ---------------------------------------------------------------------------


def validate_bytes_sync(
    data: bytes,
    *,
    kind: UploadKind,
    filename: str,
) -> None:
    """Validate raw bytes as if they were an upload.

    Used for server-side ingestion paths where the bytes did not
    arrive via multipart upload (e.g. a file read from a profile import archive).

    Args:
        data: Raw byte payload to validate.
        kind: Logical content type to validate against.
        filename: Logical filename used for filename and extension
            checks. Server-generated names only.

    Raises:
        DomainError: 400/413/415/500 mapped from safeuploads.
    """
    _validate_file(io.BytesIO(data), filename, kind=kind)


def save_validated_bytes_sync(
    data: bytes,
    *,
    kind: UploadKind,
    upload_dir: str,
    filename: str,
) -> str:
    """Validate raw bytes then persist them to ``upload_dir/filename``.

    Equivalent of :func:`save_validated_upload_sync` for byte payloads
    obtained outside the multipart pipeline (Garmin downloads, migrations).

    Args:
        data: Raw byte payload.
        kind: Logical content type.
        upload_dir: Trusted destination directory.
        filename: **Server-generated** filename within ``upload_dir``.

    Returns:
        Absolute filesystem path of the saved file.

    Raises:
        DomainError: 400/413/415/500 depending on failure mode.
    """
    validate_bytes_sync(data, kind=kind, filename=filename)
    try:
        os.makedirs(upload_dir, exist_ok=True)
        destination = _resolve_upload_path(upload_dir, filename)
        _bytes_to_path_sync(data, destination, max_bytes_for(kind))
        return str(destination)
    except core_exceptions.DomainError:
        raise
    except Exception as err:
        logger.debug("save_validated_bytes_sync failed", exc_info=err)
        raise core_exceptions.ProcessingError("Failed to save file") from err


# ---------------------------------------------------------------------------
# Zip-slip-safe extraction
# ---------------------------------------------------------------------------

# Per-entry safety caps for extract_validated_zip_sync. These mirror the
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


def _extract_to_staging(
    zip_path: Path,
    dest_dir: Path,
    max_entries: int | None,
) -> tuple[Path, list[tuple[Path, Path]]]:
    """Extract ``zip_path`` into a staging directory under ``dest_dir``.

    Performs zip-slip-safe extraction into a private staging dir with
    per-entry and total-size enforcement. Skips directory entries;
    rejects symlinks; refuses duplicate and existing targets.
    """
    extracted: list[tuple[Path, Path]] = []
    seen_targets: set[Path] = set()
    staging_dir: Path | None = None
    total_bytes = 0
    dest_resolved = dest_dir.resolve()

    try:
        with zipfile.ZipFile(zip_path, "r") as zip_ref:
            members = zip_ref.infolist()
            if max_entries is not None and len(members) > max_entries:
                raise core_exceptions.InvalidInputError(
                    f"Archive contains {len(members)} entries; maximum allowed is {max_entries}"
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
                    raise core_exceptions.InvalidInputError(f"Archive contains symlink entry: {member.filename!r}")

                target = _is_safe_extraction_target(member.filename, dest_resolved)
                if target is None:
                    raise core_exceptions.InvalidInputError(f"Archive entry escapes destination: {member.filename!r}")

                if target in seen_targets:
                    raise core_exceptions.InvalidInputError(f"Archive contains duplicate target: {member.filename!r}")
                if target.exists():
                    raise core_exceptions.InvalidInputError(f"Archive target already exists: {member.filename!r}")
                seen_targets.add(target)

                # Per-entry uncompressed size guard (declared size).
                if member.file_size > _MAX_EXTRACTED_ENTRY_BYTES:
                    raise core_exceptions.PayloadTooLargeError("Archive entry exceeds maximum entry size")
                total_bytes += member.file_size
                if total_bytes > _MAX_TOTAL_EXTRACTED_BYTES:
                    raise core_exceptions.PayloadTooLargeError("Archive total uncompressed size exceeds maximum")

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
                                raise core_exceptions.PayloadTooLargeError("Archive entry exceeds maximum entry size")
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
        DomainError: 400 when a final target is unsafe or exists.
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
                raise core_exceptions.InvalidInputError("Archive entry escapes destination") from err

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
                raise core_exceptions.InvalidInputError("Archive entry escapes destination") from err

            if final_resolved.exists():
                raise core_exceptions.InvalidInputError("Archive target already exists")

            try:
                # ``os.link`` is atomic but requires the staging dir
                # and ``dest_dir`` to live on the same filesystem. We
                # guarantee this by creating ``staging_dir`` via
                # ``tempfile.mkdtemp(dir=dest_resolved)`` in
                # :func:`_extract_to_staging`. Do not relocate
                # the staging dir without revisiting this contract.
                os.link(staged_path, final_resolved)
            except FileExistsError as err:
                raise core_exceptions.InvalidInputError("Archive target already exists") from err
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


# ---------------------------------------------------------------------------
# Path-bounded filesystem helpers
# ---------------------------------------------------------------------------


def _resolve_within(path: str | os.PathLike[str], base_dir: Path) -> Path:
    """Resolve ``path`` and verify it stays under ``base_dir``.

    Symlinks are followed via ``Path.resolve``; the resolved target
    must be strictly inside ``base_dir``.

    Args:
        path: Filesystem path to verify.
        base_dir: Trusted base directory (already resolved).

    Returns:
        Resolved :class:`Path`.

    Raises:
        DomainError: 400 when the resolved path escapes ``base_dir``.
    """
    resolved = Path(os.fspath(path)).resolve()
    try:
        resolved.relative_to(base_dir)
    except ValueError as err:
        raise core_exceptions.InvalidInputError("Path escapes the allowed directory") from err
    return resolved


def move_within(
    src: str | os.PathLike[str],
    dest_dir: str | os.PathLike[str],
    *,
    filename: str,
    src_base_dir: str | os.PathLike[str] | None = None,
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
            no-overwrite contract of :func:`extract_validated_zip_sync`.
            Callers that intentionally need to replace an existing
            file must opt in explicitly.

    Returns:
        Resolved destination :class:`Path`.

    Raises:
        DomainError: 400 for unsafe filename / containment
            violations or pre-existing destination, 500 for I/O
            failures.
    """
    dest_dir_str = os.fspath(dest_dir)
    try:
        os.makedirs(dest_dir_str, exist_ok=True)
        destination = _resolve_upload_path(dest_dir_str, filename)
        if not overwrite and destination.exists():
            raise core_exceptions.InvalidInputError("Destination file already exists")
        source = Path(os.fspath(src)).resolve()
        if src_base_dir is not None:
            source = _resolve_within(source, Path(os.fspath(src_base_dir)).resolve())
        shutil.move(source, destination)
        return destination
    except core_exceptions.DomainError:
        raise
    except (OSError, shutil.Error) as err:
        logger.debug("move_within failed", exc_info=err)
        raise core_exceptions.ProcessingError("Failed to move file") from err


def safe_remove_within(
    path: str | os.PathLike[str],
    *,
    base_dir: str | os.PathLike[str],
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
        DomainError: 400 when ``path`` escapes ``base_dir``.
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
        logger.warning("safe_remove_within failed", exc_info=err, extra=core_logger.context(file_name=target.name))
        return False


# ---------------------------------------------------------------------------
# Generic on-disk file helpers
# ---------------------------------------------------------------------------


def sha256_file(file_path: str | os.PathLike[str]) -> str:
    """Return the hex SHA-256 of a file's contents, streamed in chunks.

    Streaming (rather than reading the whole file) keeps memory bounded for the
    large payloads this codebase handles. Callers use the digest as a stable
    content fingerprint — e.g. to make re-importing an identical file a no-op.

    Args:
        file_path: File to hash.

    Returns:
        The lowercase hex digest.
    """
    digest = hashlib.sha256()
    with open(file_path, "rb") as handle:
        for chunk in iter(lambda: handle.read(_STREAM_CHUNK_BYTES), b""):
            digest.update(chunk)
    return digest.hexdigest()


def remove_files(file_paths: Iterable[str | os.PathLike[str]]) -> None:
    """Best-effort removal of files, logging (not raising) on failure.

    Used to clean up artifacts left behind by a failed multi-step operation, where
    a cleanup failure must not mask the original error.

    Args:
        file_paths: Files to remove if they still exist.

    Returns:
        None.
    """
    for file_path in file_paths:
        try:
            if os.path.isfile(file_path):
                os.remove(file_path)
        except OSError as err:
            logger.warning(
                "Failed to clean up a file",
                exc_info=err,
                extra=core_logger.context(file_name=os.path.basename(file_path)),
            )


def decompress_gzip(file_path: str | os.PathLike[str]) -> tuple[str, str]:
    """Decompress a ``.gz`` file to a temp file with a bounded output size.

    The output is capped at the same limit a direct activity upload gets, so a
    decompression bomb cannot fill the disk (defense in depth: the wrapping
    ``.gz`` upload is already size-checked before it reaches here). The source
    ``.gz`` is left in place: the caller removes it once the payload has been
    imported, so a failed import still has the user's original to hand back.
    The returned temp file is the caller's to remove.

    Args:
        file_path: Path to the gzipped file.

    Returns:
        A ``(temp_file_path, inner_extension)`` tuple, where the extension is
        derived from the filename inside the ``.gz`` (e.g. ``".fit"``).

    Raises:
        DomainError: 400 for invalid gzip content, 413 when the decompressed
            content exceeds the allowed size.
    """
    path = Path(os.fspath(file_path))

    inner_filename = path.stem  # eg "activity_1234567890.fit"
    inner_file_extension = Path(inner_filename).suffix
    temp_file_path: str | None = None
    bytes_written = 0

    try:
        with (
            gzip.open(path, "rb") as gzipped_file,
            tempfile.NamedTemporaryFile(suffix=inner_file_extension, delete=False) as temp_file,
        ):
            temp_file_path = temp_file.name
            while True:
                chunk = gzipped_file.read(_STREAM_CHUNK_BYTES)
                if not chunk:
                    break
                bytes_written += len(chunk)
                if bytes_written > _MAX_ACTIVITY_BYTES:
                    temp_file.close()
                    with contextlib.suppress(OSError):
                        os.remove(temp_file_path)
                    raise core_exceptions.PayloadTooLargeError("Decompressed file exceeds maximum allowed size")
                temp_file.write(chunk)
            temp_file.flush()

        logger.debug(
            "Decompressed <path> with inner type <inner_file_extension> to <temp_file_path>",
            extra=core_logger.context(
                path=str(path), inner_file_extension=inner_file_extension, temp_file_path=temp_file_path
            ),
        )

        return temp_file_path, inner_file_extension
    except core_exceptions.DomainError:
        raise
    except (OSError, EOFError, gzip.BadGzipFile) as err:
        if temp_file_path is not None:
            with contextlib.suppress(OSError):
                os.remove(temp_file_path)
        raise core_exceptions.InvalidInputError("Invalid gzip file") from err


def extract_validated_zip_sync(
    zip_path: str | os.PathLike[str],
    *,
    dest_dir: str | os.PathLike[str],
    per_entry_kind: UploadKind | None = None,
    max_entries: int | None = None,
) -> list[Path]:
    """Extract ``zip_path`` into ``dest_dir`` with zip-slip safety.

    The ZIP archive itself MUST already have been validated (it arrived
    through :func:`save_validated_bytes_sync` or
    :func:`save_validated_upload_sync`); this helper enforces *consumer*
    safety during iteration.

    Args:
        zip_path: Path of the ZIP archive to extract.
        dest_dir: Destination directory; created if missing.
        per_entry_kind: When provided, every extracted entry is
            re-validated via :func:`validate_local_file_sync` against the
            given :class:`UploadKind` and removed if invalid.
        max_entries: Hard cap on number of entries; defaults to the
            module-wide ``_MAX_FILES_SAME_TYPE`` if not specified.

    Returns:
        List of extracted file paths under ``dest_dir``.

    Raises:
        DomainError: 400 for zip-slip / symlink / unsafe entries,
            413 for size-cap violations, 500 for I/O failures.
    """
    if max_entries is None:
        max_entries = _MAX_FILES_SAME_TYPE
    dest_path = Path(os.fspath(dest_dir))
    os.makedirs(dest_path, exist_ok=True)

    staging_dir: Path | None = None
    try:
        staging_dir, extracted = _extract_to_staging(Path(os.fspath(zip_path)), dest_path, max_entries)
    except core_exceptions.DomainError:
        raise
    except (zipfile.BadZipFile, OSError) as err:
        logger.warning("extract_validated_zip_sync failed", exc_info=err)
        raise core_exceptions.InvalidInputError("Failed to extract archive") from err

    try:
        if per_entry_kind is not None:
            kept: list[tuple[Path, Path]] = []
            for staged_entry, final_entry in extracted:
                try:
                    validate_local_file_sync(staged_entry, kind=per_entry_kind, filename=final_entry.name)
                except core_exceptions.DomainError:
                    with contextlib.suppress(OSError):
                        staged_entry.unlink(missing_ok=True)
                    logger.warning(
                        "extract_validated_zip_sync dropped an invalid entry",
                        extra=core_logger.context(entry=final_entry.name),
                    )
                    continue
                kept.append((staged_entry, final_entry))
            extracted = kept

        try:
            return _promote_extracted_files_sync(extracted, dest_path.resolve())
        except core_exceptions.DomainError:
            raise
        except OSError as err:
            logger.debug("extract_validated_zip_sync promotion failed", exc_info=err)
            raise core_exceptions.ProcessingError("Failed to promote extracted files") from err
    finally:
        if staging_dir is not None:
            shutil.rmtree(staging_dir, ignore_errors=True)


#: Caps for a bulk-import archive, which is read member by member and never
#: extracted to disk wholesale, so they are looser than the extraction caps: a
#: Strava export holds thousands of activity files.
MAX_ARCHIVE_MEMBERS = 20_000

#: Largest archive member read into memory (a manifest or a photo); activity files
#: are streamed to disk instead.
MAX_READ_MEMBER_BYTES = 50 * 1024 * 1024
MAX_ARCHIVE_UNCOMPRESSED_BYTES = 8 * 1024 * 1024 * 1024


@dataclass(frozen=True)
class ZipMember:
    """One regular file inside an archive.

    Attributes:
        name: The member's path inside the archive, with ``/`` separators.
        size: Its uncompressed size in bytes.
    """

    name: str
    size: int


def save_text_upload_sync(file: UploadFile, *, upload_dir: str, filename: str, max_bytes: int) -> str:
    """Stream a small text upload (a CSV) to a server-named file, capped on bytes.

    No signature validator covers plain text, so the protection is the cap and a
    server-generated name; the caller parses the content with a bounded reader.

    Args:
        file: The incoming upload.
        upload_dir: Trusted destination directory.
        filename: **Server-generated** filename within ``upload_dir``.
        max_bytes: Hard cap on bytes accepted.

    Returns:
        Absolute filesystem path of the saved file.

    Raises:
        PayloadTooLargeError: When the upload exceeds ``max_bytes``.
    """
    os.makedirs(upload_dir, exist_ok=True)
    destination = _resolve_upload_path(upload_dir, filename)
    _stream_to_path_sync(file, destination, max_bytes)
    return str(destination)


def list_zip_members(zip_path: str | os.PathLike[str], *, max_entries: int | None = None) -> list[ZipMember]:
    """List an archive's regular files after checking it is safe to read by name.

    Rejects what extraction would reject (traversal and absolute names, symlinks,
    duplicates, too many entries, an entry or total beyond the size caps) without
    reading any member's bytes, so a caller can refuse an archive up front and then
    read members one at a time with :func:`copy_zip_member`.

    Args:
        zip_path: Path of the ZIP archive.
        max_entries: Hard cap on entries; defaults to :data:`MAX_ARCHIVE_MEMBERS`.

    Returns:
        The archive's regular files, in archive order.

    Raises:
        InvalidInputError: When the archive is malformed or unsafe.
        PayloadTooLargeError: When a size cap is exceeded.
    """
    limit = MAX_ARCHIVE_MEMBERS if max_entries is None else max_entries
    members: list[ZipMember] = []
    seen: set[str] = set()
    total = 0
    try:
        with zipfile.ZipFile(zip_path, "r") as zip_ref:
            infos = zip_ref.infolist()
            if len(infos) > limit:
                raise core_exceptions.InvalidInputError(
                    f"Archive contains {len(infos)} entries; maximum allowed is {limit}"
                )
            for info in infos:
                if info.is_dir():
                    continue
                mode = (info.external_attr >> 16) & 0xFFFF
                if mode and (mode & 0o170000) == 0o120000:
                    raise core_exceptions.InvalidInputError("Archive contains a symlink entry")
                name = info.filename.replace("\\", "/")
                if (
                    not name
                    or name.startswith("/")
                    or "\x00" in name
                    or ".." in PurePosixPath(name).parts
                    or PureWindowsPath(name).drive
                ):
                    raise core_exceptions.InvalidInputError("Archive contains an unsafe entry name")
                if name in seen:
                    raise core_exceptions.InvalidInputError("Archive contains a duplicate entry")
                seen.add(name)
                if info.file_size > _MAX_EXTRACTED_ENTRY_BYTES:
                    raise core_exceptions.PayloadTooLargeError("Archive entry exceeds the allowed size")
                total += info.file_size
                if total > MAX_ARCHIVE_UNCOMPRESSED_BYTES:
                    raise core_exceptions.PayloadTooLargeError("Archive contents exceed the allowed size")
                members.append(ZipMember(name=name, size=info.file_size))
    except zipfile.BadZipFile as err:
        raise core_exceptions.InvalidInputError("Invalid ZIP archive") from err
    return members


def copy_zip_member(
    zip_ref: zipfile.ZipFile,
    member_name: str,
    destination: str | os.PathLike[str],
    *,
    max_bytes: int | None = None,
) -> int:
    """Stream one archive member to a path the caller chose.

    The destination is never derived from the member name, so a hostile name
    cannot place the file anywhere. The copy is capped on bytes actually written,
    not on the size the archive header claims.

    Args:
        zip_ref: An open archive.
        member_name: The member to read, as listed by :func:`list_zip_members`.
        destination: Where to write it.
        max_bytes: Cap on bytes written; defaults to the activity-file cap.

    Returns:
        The number of bytes written.

    Raises:
        InvalidInputError: When the member does not exist.
        PayloadTooLargeError: When the member inflates beyond the cap; the partial
            file is removed.
    """
    cap = _MAX_ACTIVITY_BYTES if max_bytes is None else max_bytes
    try:
        source = zip_ref.open(member_name, "r")
    except KeyError as err:
        raise core_exceptions.InvalidInputError("Archive entry not found") from err

    written = 0
    try:
        with source, open(destination, "wb") as out:
            while chunk := source.read(_STREAM_CHUNK_BYTES):
                written += len(chunk)
                if written > cap:
                    raise core_exceptions.PayloadTooLargeError("Archive entry exceeds the allowed size")
                out.write(chunk)
    except BaseException:
        with contextlib.suppress(OSError):
            os.remove(destination)
        raise
    return written
