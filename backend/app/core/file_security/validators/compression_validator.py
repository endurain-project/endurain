"""
Compression Security Validator Module

Handles validation of ZIP compression ratios and zip bomb detection.
"""
import io
import time
import zipfile
from typing import Tuple, TYPE_CHECKING

import core.logger as core_logger
from .base import BaseValidator

if TYPE_CHECKING:
    from ..config import FileSecurityConfig


class CompressionSecurityValidator(BaseValidator):

    def __init__(self, config: "FileSecurityConfig"):
        super().__init__(config)

    def validate_zip_compression_ratio(
        self, file_content: bytes, compressed_size: int
    ) -> Tuple[bool, str]:
        """
        Validate ZIP compression ratio to detect zip bombs.
        
        Args:
            file_content: The ZIP file content as bytes
            compressed_size: The compressed file size
            
        Returns:
            Tuple[bool, str]: (is_valid, error_message)
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
                    return (
                        False,
                        f"ZIP contains too many files: {file_count}. Maximum allowed: {self.config.limits.max_zip_entries}",
                    )

                # Analyze each entry in the ZIP
                for entry in zip_entries:
                    # Check for timeout
                    if time.time() - start_time > self.config.limits.zip_analysis_timeout:
                        return (
                            False,
                            f"ZIP analysis timeout after {self.config.limits.zip_analysis_timeout}s - potential zip bomb",
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
                            return (
                                False,
                                f"Excessive compression ratio detected: {compression_ratio:.1f}:1 for '{entry.filename}'. Maximum allowed: {self.config.limits.max_compression_ratio}:1",
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
                        return (
                            False,
                            f"Individual file too large: '{entry.filename}' would expand to {uncompressed_size // (1024*1024)}MB. "
                            f"Maximum allowed: {self.config.limits.max_individual_file_size // (1024*1024)}MB",
                        )

                # Check total uncompressed size
                if total_uncompressed_size > self.config.limits.max_uncompressed_size:
                    return (
                        False,
                        f"Total uncompressed size too large: {total_uncompressed_size // (1024*1024)}MB. Maximum allowed: {self.config.limits.max_uncompressed_size // (1024*1024)}MB",
                    )

                # Check overall compression ratio
                if total_compressed_size > 0:
                    overall_compression_ratio = (
                        total_uncompressed_size / total_compressed_size
                    )
                    if overall_compression_ratio > self.config.limits.max_compression_ratio:
                        return (
                            False,
                            f"Overall compression ratio too high: {overall_compression_ratio:.1f}:1. Maximum allowed: {self.config.limits.max_compression_ratio}:1",
                        )

                # Reject nested archives (potential security risk)
                if nested_archives:
                    core_logger.print_to_log(
                        "Detected nested archives in ZIP file. Upload rejected for security.",
                        "warning",
                    )
                    return (False, "Nested archives are not allowed")

                # Log analysis results
                core_logger.print_to_log(
                    f"ZIP analysis: {file_count} files, {total_uncompressed_size // (1024*1024)}MB uncompressed, "
                    f"max ratio: {max_compression_ratio:.1f}:1, overall ratio: {overall_compression_ratio:.1f}:1",
                    "debug",
                )

                return True, "ZIP compression validation passed"

        except zipfile.BadZipFile:
            return False, "Invalid or corrupted ZIP file"
        except zipfile.LargeZipFile:
            return False, "ZIP file too large to process safely"
        except MemoryError:
            return (
                False,
                "ZIP file requires too much memory to process - potential zip bomb",
            )
        except Exception as err:
            core_logger.print_to_log(
                f"Error during ZIP compression validation: {err}", "warning", exc=err
            )
            return False, f"ZIP validation failed: {str(err)}"
    
    def validate(self, file_content: bytes, compressed_size: int) -> Tuple[bool, str]:
        """Compatibility method for base class interface."""
        return self.validate_zip_compression_ratio(file_content, compressed_size)