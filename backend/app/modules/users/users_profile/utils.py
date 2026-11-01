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
from typing import Any, TypeVar

import psutil
from pydantic import BaseModel

import core.logger as core_logger
from modules.users.users_profile.exceptions import (
    MemoryAllocationError,
)

logger = core_logger.get_logger(__name__)

# Type variable for performance config classes
T_PerformanceConfig = TypeVar("T_PerformanceConfig", bound="BasePerformanceConfig")


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
    def _get_tier_configs(cls) -> dict[str, dict[str, Any]]:
        """Get configuration tiers for different memory levels.

        Returns:
            Dictionary mapping tier names to config dicts.

        Raises:
            NotImplementedError: Must be implemented by subclass.
        """
        raise NotImplementedError("Subclasses must implement _get_tier_configs")

    @classmethod
    def get_auto_config(cls: type[T_PerformanceConfig]) -> T_PerformanceConfig:
        """Create config automatically based on system memory.

        Returns:
            Configuration instance for detected tier.
        """
        try:
            tier, _ = detect_system_memory_tier()
            tier_configs = cls._get_tier_configs()

            if tier in tier_configs:
                config_dict = tier_configs[tier]
                return cls(**config_dict)
            else:
                logger.warning("Unknown memory tier, using the default config", extra=core_logger.context(tier=tier))
                return cls()
        except Exception as err:
            logger.warning("Failed to create the auto config, using defaults", exc_info=err)
            return cls()


# Export utility functions
def sqlalchemy_obj_to_dict(obj: Any) -> dict[str, Any]:
    """Convert a SQLAlchemy model or Pydantic schema to a dictionary.

    Args:
        obj: SQLAlchemy model instance, Pydantic model, or other object.

    Returns:
        Dictionary with column/field names and values.
    """
    if hasattr(obj, "__table__"):
        return {c.name: getattr(obj, c.name) for c in obj.__table__.columns}
    if isinstance(obj, BaseModel):
        return obj.model_dump(mode="json")
    return obj


def write_json_to_zip(
    zipf: zipfile.ZipFile,
    filename: str,
    data: list[dict[str, Any]] | dict[str, Any] | list[Any] | None,
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
    batches: Iterable[Sequence[Any]],
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
        "media": 0,
        "activity_files": 0,
        "activities": 0,
        "activity_laps": 0,
        "activity_sets": 0,
        "activity_streams": 0,
        "activity_workout_steps": 0,
        "activity_media": 0,
        "activity_exercise_titles": 0,
        "gears": 0,
        "gear_components": 0,
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
