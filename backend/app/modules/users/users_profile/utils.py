"""Profile utility functions for data operations.

This module provides helper functions for:
- SQLAlchemy to dict conversion
- Memory and timeout monitoring
- ZIP file operations
- Performance configuration management
"""

import json
import time
import zipfile
from collections.abc import Iterable, Sequence
from typing import Any, Self

import psutil
from pydantic import BaseModel

import core.logger as core_logger
from modules.users.users_profile.exceptions import (
    FileFormatError,
    FileSizeError,
    JSONParseError,
    MemoryAllocationError,
)

logger = core_logger.get_logger(__name__)


class BasePerformanceConfig:
    """Base configuration for performance settings.

    Attributes:
        batch_size: Number of items to process in a batch.
        max_memory_mb: Maximum memory usage in megabytes.
        timeout_seconds: Operation timeout in seconds.
        chunk_size: Size of data chunks in bytes.
        enable_memory_monitoring: Enable memory monitoring.
    """

    def __init__(
        self,
        batch_size: int = 1000,
        max_memory_mb: int = 1024,
        timeout_seconds: int = 3600,
        chunk_size: int = 8192,
        enable_memory_monitoring: bool = True,
    ):
        """Set the operation limits; unset values take the defaults."""
        self.batch_size = batch_size
        self.max_memory_mb = max_memory_mb
        self.timeout_seconds = timeout_seconds
        self.chunk_size = chunk_size
        self.enable_memory_monitoring = enable_memory_monitoring

    @classmethod
    def _get_tier_configs(cls) -> dict[str, Self]:
        """Get configuration tiers for different memory levels.

        Returns:
            Dictionary mapping tier names to their configs.

        Raises:
            NotImplementedError: Must be implemented by subclass.
        """
        raise NotImplementedError("Subclasses must implement _get_tier_configs")

    @classmethod
    def get_auto_config(cls) -> Self:
        """Create config automatically based on system memory.

        Returns:
            Configuration instance for detected tier, or the default
            configuration when the tier has no entry.

        Raises:
            NotImplementedError: If the subclass does not implement
                ``_get_tier_configs``.
        """
        tier, _ = detect_system_memory_tier()
        tier_configs = cls._get_tier_configs()

        if tier in tier_configs:
            return tier_configs[tier]
        logger.warning("Unknown memory tier, using the default config", extra=core_logger.context(tier=tier))
        return cls()


# Export utility functions
def model_to_dict(model: BaseModel) -> dict[str, Any]:
    """Return a schema as the JSON object an archive stores.

    Args:
        model: The schema to export.

    Returns:
        The schema's fields, with dates and decimals as their JSON form.
    """
    return model.model_dump(mode="json")


def write_json_to_zip(
    zipf: zipfile.ZipFile,
    filename: str,
    data: list[dict[str, Any]] | dict[str, Any] | None,
    counts: dict[str, int],
    ensure_ascii: bool = False,
) -> None:
    """Write JSON data to ZIP file and update counts.

    Args:
        zipf: ZipFile instance to write to.
        filename: Name of file in ZIP.
        data: Data to serialize as JSON.
        counts: Dictionary to update with item counts.
        ensure_ascii: Whether to ensure ASCII encoding.
    """
    if data is None:
        data = []
    counts[filename.split("/")[-1].replace(".json", "")] = len(data) if isinstance(data, (list, tuple)) else 1
    zipf.writestr(
        filename,
        json.dumps(data, default=str, ensure_ascii=ensure_ascii),
    )


def write_json_array_to_zip(
    zipf: zipfile.ZipFile,
    filename: str,
    batches: Iterable[Sequence[dict[str, Any]]],
    counts: dict[str, int],
    ensure_ascii: bool = False,
) -> None:
    """Stream a JSON array into a ZIP entry one batch at a time and update counts.

    The entry is byte-for-byte what :func:`write_json_to_zip` writes for the same items, but only one
    batch is held at a time. Nothing else may be written to the archive while ``batches`` is consumed,
    since the entry is open until it is exhausted.

    Args:
        zipf: ZipFile instance to write to.
        filename: Name of file in ZIP.
        batches: Batches of JSON-serializable items, read lazily.
        counts: Dictionary to update with the item count.
        ensure_ascii: Whether to ensure ASCII encoding.
    """
    total = 0
    # Its size is unknown until it is written, so zip64 is allowed up front.
    with zipf.open(filename, "w", force_zip64=True) as entry:
        entry.write(b"[")
        for batch in batches:
            for item in batch:
                if total:
                    entry.write(b", ")
                entry.write(json.dumps(item, default=str, ensure_ascii=ensure_ascii).encode("utf-8"))
                total += 1
        entry.write(b"]")
    counts[filename.split("/")[-1].replace(".json", "")] = total


class ZipArchiveWriter:
    """The export archive a profile section writes to.

    Every JSON write sets ``counts[stem]`` to the number of records written.
    """

    def __init__(self, zipf: zipfile.ZipFile, counts: dict[str, int]):
        """Bind the writer to an open ZIP and the counts it updates."""
        self._zipf = zipf
        self._counts = counts

    def write_json(self, path: str, records: Sequence[BaseModel]) -> None:
        """Write records as one JSON array entry.

        Args:
            path: Entry path inside the archive.
            records: The records to serialize.
        """
        write_json_to_zip(self._zipf, path, [model_to_dict(record) for record in records], self._counts)

    def write_json_stream(self, path: str, batches: Iterable[Sequence[BaseModel]]) -> None:
        """Write records as one JSON array entry, holding one batch at a time.

        Args:
            path: Entry path inside the archive.
            batches: The records to serialize, read lazily.
        """
        write_json_array_to_zip(
            self._zipf, path, ([model_to_dict(record) for record in batch] for batch in batches), self._counts
        )

    def write_bytes(self, path: str, data: bytes) -> None:
        """Write one entry as it is.

        Args:
            path: Entry path inside the archive.
            data: The entry content.
        """
        self._zipf.writestr(path, data)


class ZipArchiveReader:
    """The import archive a profile section reads from, with per-entry and archive-wide size caps."""

    def __init__(
        self,
        zipf: zipfile.ZipFile,
        *,
        max_json_bytes: int,
        max_uncompressed_bytes: int,
        max_memory_mb: int,
        enable_memory_monitoring: bool,
    ):
        """Bind the reader to an open ZIP and its limits.

        Args:
            zipf: The open archive.
            max_json_bytes: The most one JSON entry may decompress to.
            max_uncompressed_bytes: The most the whole archive may decompress to across every read.
            max_memory_mb: Memory limit checked after loading a JSON entry.
            enable_memory_monitoring: Whether the memory limit is checked.
        """
        self._zipf = zipf
        self._names = frozenset(zipf.namelist())
        self._max_json_bytes = max_json_bytes
        self._max_uncompressed_bytes = max_uncompressed_bytes
        self._max_memory_mb = max_memory_mb
        self._enable_memory_monitoring = enable_memory_monitoring
        self._uncompressed_bytes = 0

    @property
    def names(self) -> frozenset[str]:
        """The entry names in the archive."""
        return self._names

    def read_bytes(self, path: str, *, max_bytes: int) -> bytes:
        """Read a ZIP entry after checking its declared size.

        Args:
            path: Name of the entry to read.
            max_bytes: Byte cap for this entry.

        Returns:
            Entry bytes.

        Raises:
            FileSizeError: If the entry or the archive exceeds the allowed size.
        """
        return self._read(path, max_bytes)

    def _read(self, filename: str, limit: int) -> bytes:
        """Read a ZIP entry, enforcing the entry cap and the archive-wide cap.

        Args:
            filename: Name of the entry to read.
            limit: Byte cap for this entry.

        Returns:
            Entry bytes.

        Raises:
            FileSizeError: If the entry or the archive exceeds the allowed size.
        """
        info = self._zipf.getinfo(filename)
        # ``info.file_size`` comes from the central directory and a malicious archive can lie. The
        # declared-size check below is a fast pre-filter; the streaming read that follows enforces the
        # same cap against the actual decompressed bytes so a zip-bomb cannot exhaust memory.
        if info.file_size > limit:
            raise FileSizeError(
                f"ZIP entry {filename} size ({info.file_size} bytes) exceeds maximum allowed ({limit} bytes)"
            )
        chunks: list[bytes] = []
        bytes_read = 0
        chunk_size = 64 * 1024
        with self._zipf.open(info, "r") as src:
            while True:
                chunk = src.read(chunk_size)
                if not chunk:
                    break
                bytes_read += len(chunk)
                if bytes_read > limit:
                    raise FileSizeError(
                        f"ZIP entry {filename} decompressed size exceeds maximum allowed ({limit} bytes)"
                    )
                self._uncompressed_bytes += len(chunk)
                if self._uncompressed_bytes > self._max_uncompressed_bytes:
                    raise FileSizeError(
                        f"The archive's uncompressed size exceeds {self._max_uncompressed_bytes // (1024 * 1024)}MB"
                    )
                chunks.append(chunk)
        return b"".join(chunks)

    def load_json(self, path: str, *, check_memory: bool = True) -> list[dict[str, Any]]:
        """Load and parse a JSON array entry.

        Args:
            path: Name of the JSON entry to load.
            check_memory: Whether to check memory usage.

        Returns:
            The JSON objects the entry lists; an absent entry gives an empty list and an item that
            is not an object is skipped with a warning.

        Raises:
            FileSizeError: If the entry or the archive exceeds the allowed size.
            JSONParseError: If JSON parsing fails.
            MemoryAllocationError: If the memory limit is exceeded.
        """
        try:
            if path not in self._names:
                logger.warning("Expected data file not found in ZIP archive", extra=core_logger.context(filename=path))
                return []

            data = json.loads(self._read(path, self._max_json_bytes))

            if not isinstance(data, list):
                logger.warning(
                    "Expected a list in a data file, returning an empty list",
                    extra=core_logger.context(filename=path, found_type=type(data).__name__),
                )
                return []

            records = [item for item in data if isinstance(item, dict)]
            if len(records) != len(data):
                logger.warning(
                    "Skipped data file entries that are not objects",
                    extra=core_logger.context(filename=path, skipped=len(data) - len(records)),
                )

            logger.debug("Loaded items from a data file", extra=core_logger.context(count=len(records), filename=path))

            if check_memory:
                check_memory_usage(f"loading {path}", self._max_memory_mb, self._enable_memory_monitoring)

            return records
        except json.JSONDecodeError as err:
            raise JSONParseError(f"Failed to parse JSON from {path}: {err}") from err

    def load_json_part(self, path: str) -> list[dict[str, Any]]:
        """Load one part of a split JSON array entry; a bad part is logged and skipped.

        Args:
            path: Name of the part to load.

        Returns:
            The JSON objects the part lists, or an empty list when it cannot be read.
        """
        try:
            data = json.loads(self._read(path, self._max_json_bytes))
        except json.JSONDecodeError as err:
            logger.warning("Failed to parse a component file", extra=core_logger.context(filename=path, error=err))
            return []
        except (FileFormatError, FileSizeError, OSError) as err:
            logger.warning("Error loading a component file", extra=core_logger.context(filename=path, error=err))
            return []
        if not isinstance(data, list):
            logger.warning(
                "Expected a list in a component file",
                extra=core_logger.context(filename=path, found_type=type(data).__name__),
            )
            return []
        return [item for item in data if isinstance(item, dict)]


def check_timeout(
    timeout_seconds: int | None,
    start_time: float,
    exception_class: type[Exception],
    operation_type: str,
) -> None:
    """Check if operation has exceeded timeout.

    Args:
        timeout_seconds: Timeout limit in seconds or None.
        start_time: Operation start time from time.time().
        exception_class: Exception type to raise on timeout.
        operation_type: Description of operation for error.

    Raises:
        exception_class: If timeout is exceeded.
    """
    if timeout_seconds and (time.time() - start_time) > timeout_seconds:
        raise exception_class(f"{operation_type} exceeded {timeout_seconds} seconds")


def get_memory_usage_mb(enable_monitoring: bool = True) -> float:
    """Get current process memory usage in megabytes.

    Args:
        enable_monitoring: Whether monitoring is enabled.

    Returns:
        Memory usage in MB, or 0.0 if disabled or error.
    """
    try:
        if not enable_monitoring:
            return 0.0
        process = psutil.Process()
        return process.memory_info().rss / (1024 * 1024)  # Convert to MB
    except Exception as err:
        logger.warning("Failed to get memory usage", exc_info=err)
        return 0.0


def check_memory_usage(
    operation: str,
    max_memory_mb: int,
    enable_monitoring: bool = True,
    memory_intensive_operations: list[str] | None = None,
) -> None:
    """Check memory usage and raise error if limit exceeded.

    Args:
        operation: Description of current operation.
        max_memory_mb: Maximum allowed memory in MB.
        enable_monitoring: Whether monitoring is enabled.
        memory_intensive_operations: List of intensive ops.

    Raises:
        MemoryAllocationError: If memory limit exceeded.
    """
    if not enable_monitoring:
        return

    current_memory = get_memory_usage_mb(enable_monitoring)

    # Default memory-intensive operations if none provided
    if memory_intensive_operations is None:
        memory_intensive_operations = [
            "ZIP file loading",
            "activities import",
            "activity components",
            "JSON parsing",
            "activity collection",
            "data collection",
            "ZIP creation",
            "file streaming",
        ]

    is_memory_intensive = any(op in operation.lower() for op in memory_intensive_operations)

    # Use a higher threshold for memory-intensive operations
    effective_limit = max_memory_mb
    if is_memory_intensive:
        effective_limit = int(max_memory_mb * 1.5)  # Allow 50% more for intensive ops

    if current_memory > effective_limit:
        error_msg = (
            f"Memory usage ({current_memory:.1f}MB) critically exceeded limit "
            f"({max_memory_mb}MB, effective: {effective_limit:.1f}MB) during {operation}"
        )
        raise MemoryAllocationError(error_msg)

    # Warn at 90%
    if current_memory > max_memory_mb * 0.9:
        logger.info(
            "High memory usage",
            extra=core_logger.context(current_memory=current_memory, max_memory_mb=max_memory_mb, operation=operation),
        )


def initialize_operation_counts(include_user_count: bool = False) -> dict[str, int]:
    """Initialize dictionary for tracking operation counts.

    Args:
        include_user_count: Whether to include user count.

    Returns:
        Dictionary with all count keys initialized to 0.
    """
    return {
        "health_weight": 0,
        "health_targets": 0,
        "health_sleep": 0,
        "health_steps": 0,
        "health_water": 0,
        "health_fasting": 0,
        "health_poop": 0,
        "user_images": 0,
        "user": 1 if include_user_count else 0,
        "user_default_gear": 0,
        "user_goals": 0,
        "user_identity_providers": 0,
        "user_integrations": 0,
        "user_privacy_settings": 0,
    }


def detect_system_memory_tier() -> tuple[str, int]:
    """Detect system memory tier based on available memory.

    Returns:
        Tuple of tier name and available memory in MB.
    """
    try:
        memory = psutil.virtual_memory()
        available_mb = memory.available // (1024 * 1024)

        if available_mb > 2048:  # > 2GB available
            return "high", available_mb
        elif available_mb > 1024:  # > 1GB available
            return "medium", available_mb
        else:  # Low memory system
            return "low", available_mb
    except Exception as err:
        logger.warning("Failed to detect system memory, using defaults", exc_info=err)
        return "medium", 1024  # Default to medium tier with 1GB
