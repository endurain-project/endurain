"""
Validates ZIP compression ratios and detects zip bombs.
"""

from __future__ import annotations

import io
import time
import zipfile
import logging

from typing import TYPE_CHECKING
from .base import BaseValidator
from ..exceptions import (
    ZipBombError,
    CompressionSecurityError,
    FileProcessingError,
    ErrorCode,
)

if TYPE_CHECKING:
    from ..config import FileSecurityConfig


logger = logging.getLogger(__name__)


class CompressionSecurityValidator(BaseValidator):
    """
    Validates ZIP uploads against zip bombs and compression attacks.

    Attributes:
        config: Security configuration for validation limits.
    """

    def __init__(self, config: FileSecurityConfig):
        """
        Initialize the compression validator.

        Args:
            config: Security configuration with compression limits.
        """
        super().__init__(config)

    def validate_zip_compression_ratio(
        self, file_content: bytes, compressed_size: int
    ) -> None:
        """
        Validate ZIP archive against security limits.

        Args:
            file_content: Raw bytes of the ZIP archive.
            compressed_size: Size of the compressed archive in bytes.

        Raises:
            ZipBombError: If compression ratio exceeds maximum allowed
                or total uncompressed size is too large.
            CompressionSecurityError: If ZIP structure is invalid, too
                many entries, nested archives detected, or individual
                file too large.
            FileProcessingError: If unexpected error occurs during
                validation such as memory errors or I/O errors.
        """
        try:
            # Create a BytesIO object from file content for zipfile analysis
            zip_bytes = io.BytesIO(file_content)

            # Track analysis metrics
            total_uncompressed_size = 0
            total_compressed_size = compressed_size
            file_count = 0
            nested_archives = []
            max_compression_ratio = 0
            overall_compression_ratio = 0  # Initialize to avoid unbound variable

            # Analyze ZIP file structure with timeout protection
            start_time = time.time()

            with zipfile.ZipFile(zip_bytes, "r") as zip_file:
                # Check for excessive number of files
                zip_entries = zip_file.infolist()
                file_count = len(zip_entries)

                if file_count > self.config.limits.max_zip_entries:
                    logger.warning(
                        "ZIP contains too many files",
                        extra={
                            "error_type": "zip_too_many_entries",
                            "file_count": file_count,
                            "max_entries": self.config.limits.max_zip_entries,
                        },
                    )
                    raise CompressionSecurityError(
                        message=f"ZIP contains too many files: {file_count}. "
                        f"Maximum allowed: {self.config.limits.max_zip_entries}",
                        error_code=ErrorCode.ZIP_TOO_MANY_ENTRIES,
                    )

                # Analyze each entry in the ZIP
                for entry in zip_entries:
                    # Check for timeout
                    if (
                        time.time() - start_time
                        > self.config.limits.zip_analysis_timeout
                    ):
                        logger.error(
                            "ZIP analysis timeout",
                            extra={
                                "error_type": "zip_analysis_timeout",
                                "timeout": self.config.limits.zip_analysis_timeout,
                            },
                        )
                        raise ZipBombError(
                            message=f"ZIP analysis timeout after {self.config.limits.zip_analysis_timeout}s - potential zip bomb",
                            compression_ratio=0,
                        )

                    # Skip directories
                    if entry.is_dir():
                        continue

                    # Track uncompressed size
                    uncompressed_size = entry.file_size
                    compressed_size_entry = entry.compress_size
                    total_uncompressed_size += uncompressed_size

                    # Check individual file compression ratio
                    if compressed_size_entry > 0:  # Avoid division by zero
                        compression_ratio = uncompressed_size / compressed_size_entry
                        max_compression_ratio = max(
                            max_compression_ratio, compression_ratio
                        )

                        if compression_ratio > self.config.limits.max_compression_ratio:
                            logger.error(
                                "Excessive compression ratio detected",
                                extra={
                                    "error_type": "compression_ratio_exceeded",
                                    "file_name": entry.filename,
                                    "compression_ratio": compression_ratio,
                                    "max_ratio": self.config.limits.max_compression_ratio,
                                },
                            )
                            raise ZipBombError(
                                message=f"Excessive compression ratio detected: {compression_ratio:.1f}:1 for '{entry.filename}'. "
                                f"Maximum allowed: {self.config.limits.max_compression_ratio}:1",
                                compression_ratio=compression_ratio,
                            )

                    # Check for nested archive files
                    filename_lower = entry.filename.lower()
                    if any(
                        filename_lower.endswith(ext)
                        for ext in [".zip", ".rar", ".7z", ".tar", ".gz", ".bz2"]
                    ):
                        nested_archives.append(entry.filename)

                    # Check for excessively large individual files
                    # Use the configurable max_individual_file_size limit
                    if uncompressed_size > self.config.limits.max_individual_file_size:
                        logger.warning(
                            "Individual file too large",
                            extra={
                                "error_type": "file_too_large",
                                "file_name": entry.filename,
                                "size_mb": uncompressed_size // (1024 * 1024),
                                "max_size_mb": self.config.limits.max_individual_file_size
                                // (1024 * 1024),
                            },
                        )
                        raise CompressionSecurityError(
                            message=f"Individual file too large: '{entry.filename}' would expand to {uncompressed_size // (1024*1024)}MB. "
                            f"Maximum allowed: {self.config.limits.max_individual_file_size // (1024*1024)}MB",
                            error_code=ErrorCode.FILE_TOO_LARGE,
                        )

                # Check total uncompressed size
                if total_uncompressed_size > self.config.limits.max_uncompressed_size:
                    logger.warning(
                        "Total uncompressed size too large",
                        extra={
                            "error_type": "zip_too_large",
                            "total_size_mb": total_uncompressed_size // (1024 * 1024),
                            "max_size_mb": self.config.limits.max_uncompressed_size
                            // (1024 * 1024),
                        },
                    )
                    raise ZipBombError(
                        message=f"Total uncompressed size too large: {total_uncompressed_size // (1024*1024)}MB. "
                        f"Maximum allowed: {self.config.limits.max_uncompressed_size // (1024*1024)}MB",
                        compression_ratio=0,
                        uncompressed_size=total_uncompressed_size,
                        max_size=self.config.limits.max_uncompressed_size,
                    )

                # Check overall compression ratio
                if total_compressed_size > 0:
                    overall_compression_ratio = (
                        total_uncompressed_size / total_compressed_size
                    )
                    if (
                        overall_compression_ratio
                        > self.config.limits.max_compression_ratio
                    ):
                        logger.error(
                            "Overall compression ratio too high",
                            extra={
                                "error_type": "compression_ratio_exceeded",
                                "overall_ratio": overall_compression_ratio,
                                "max_ratio": self.config.limits.max_compression_ratio,
                            },
                        )
                        raise ZipBombError(
                            message=f"Overall compression ratio too high: {overall_compression_ratio:.1f}:1. "
                            f"Maximum allowed: {self.config.limits.max_compression_ratio}:1",
                            compression_ratio=overall_compression_ratio,
                            max_ratio=self.config.limits.max_compression_ratio,
                        )

                # Reject nested archives (potential security risk)
                if nested_archives:
                    logger.warning(
                        "Nested archives detected",
                        extra={
                            "error_type": "zip_nested_archive",
                            "nested_archives": nested_archives,
                        },
                    )
                    raise CompressionSecurityError(
                        message=f"Nested archives are not allowed: {', '.join(nested_archives)}",
                        error_code=ErrorCode.ZIP_NESTED_ARCHIVE,
                    )

                # Log analysis results
                logger.debug(
                    "ZIP analysis: %s files, %sMB uncompressed, max ratio: %.1f:1, overall ratio: %.1f:1",
                    file_count,
                    total_uncompressed_size // (1024 * 1024),
                    max_compression_ratio,
                    overall_compression_ratio,
                )

        except zipfile.BadZipFile as err:
            logger.error("Invalid or corrupted ZIP file", exc_info=True)
            raise CompressionSecurityError(
                message="Invalid or corrupted ZIP file",
                error_code=ErrorCode.ZIP_CORRUPT,
            ) from err
        except zipfile.LargeZipFile as err:
            logger.error("ZIP file too large to process", exc_info=True)
            raise CompressionSecurityError(
                message="ZIP file too large to process safely",
                error_code=ErrorCode.ZIP_TOO_LARGE,
            ) from err
        except MemoryError as err:
            logger.error("ZIP requires excessive memory", exc_info=True)
            raise ZipBombError(
                message="ZIP file requires too much memory to process - potential zip bomb",
                compression_ratio=0,
            ) from err
        except (ZipBombError, CompressionSecurityError):
            # Re-raise our own exceptions
            raise
        except Exception as err:
            logger.error(
                "Unexpected error during ZIP compression validation",
                exc_info=True,
            )
            raise FileProcessingError(
                message=f"ZIP validation failed: {str(err)}",
            ) from err

    def validate(self, file_content: bytes, compressed_size: int) -> None:
        """
        Validate the compression ratio of a ZIP file.

        Args:
            file_content: Raw bytes of the uploaded file.
            compressed_size: Size of the file after compression in bytes.

        Raises:
            ZipBombError: If compression ratio exceeds maximum allowed.
            CompressionSecurityError: If ZIP structure is invalid.
            FileProcessingError: If unexpected error occurs.
        """
        return self.validate_zip_compression_ratio(file_content, compressed_size)
