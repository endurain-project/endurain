"""ZIP content inspector for security threat detection."""

from __future__ import annotations

import io
import os
import time
import zipfile
from typing import TYPE_CHECKING

import logging
from ..enums import SuspiciousFilePattern, ZipThreatCategory, BinaryFileCategory
from ..exceptions import ZipContentError, FileProcessingError, ErrorCode

if TYPE_CHECKING:
    from ..config import FileSecurityConfig


logger = logging.getLogger(__name__)


class ZipContentInspector:
    """
    Inspects ZIP archive contents for security threats.

    Attributes:
        config: File security configuration.
    """

    def __init__(self, config: FileSecurityConfig):
        """
        Initialize ZIP inspector with configuration.

        Args:
            config: File security configuration.
        """
        self.config = config

    def inspect_zip_content(self, file_content: bytes) -> None:
        """
        Inspect ZIP archive for potential security threats.

        Args:
            file_content: Raw bytes of ZIP archive.

        Raises:
            ZipContentError: If security threats are detected in ZIP
                content such as directory traversal, symlinks, nested
                archives, or suspicious patterns.
            FileProcessingError: If ZIP structure is invalid or
                unexpected error occurs during inspection.
        """
        try:
            zip_bytes = io.BytesIO(file_content)
            threats_found = []

            # Start analysis timer
            start_time = time.time()

            with zipfile.ZipFile(zip_bytes, "r") as zip_file:
                zip_entries = zip_file.infolist()

                # Analyze each entry in the ZIP
                for entry in zip_entries:
                    # Check for timeout
                    if (
                        time.time() - start_time
                        > self.config.limits.zip_analysis_timeout
                    ):
                        logger.error(
                            "ZIP content inspection timeout",
                            extra={
                                "error_type": "zip_analysis_timeout",
                                "timeout": self.config.limits.zip_analysis_timeout,
                            },
                        )
                        raise ZipContentError(
                            message=f"ZIP content inspection timeout after {self.config.limits.zip_analysis_timeout}s",
                            threats=["Analysis timeout - potential zip bomb"],
                            error_code=ErrorCode.ZIP_ANALYSIS_TIMEOUT,
                        )

                    # Inspect individual entry
                    entry_threats = self._inspect_zip_entry(entry, zip_file)
                    threats_found.extend(entry_threats)

                # Check for ZIP structure threats
                structure_threats = self._inspect_zip_structure(zip_entries)
                threats_found.extend(structure_threats)

                # Return results
                if threats_found:
                    logger.warning(
                        "ZIP content threats detected",
                        extra={
                            "error_type": "zip_content_threat",
                            "threats": threats_found,
                            "threat_count": len(threats_found),
                        },
                    )
                    raise ZipContentError(
                        message=f"ZIP content threats detected: {'; '.join(threats_found)}",
                        threats=threats_found,
                    )

                logger.debug(
                    "ZIP content inspection passed: %s entries analyzed",
                    len(zip_entries),
                )

        except ZipContentError:
            # Re-raise our own exceptions
            raise
        except zipfile.BadZipFile as err:
            logger.error("Invalid or corrupted ZIP file structure", exc_info=True)
            raise FileProcessingError(
                message="Invalid or corrupted ZIP file structure",
                original_error=err,
            ) from err
        except Exception as err:
            logger.error(
                "Unexpected error during ZIP content inspection",
                exc_info=True,
            )
            raise FileProcessingError(
                message=f"ZIP content inspection failed: {str(err)}",
                original_error=err,
            ) from err

    def _inspect_zip_entry(
        self, entry: zipfile.ZipInfo, zip_file: zipfile.ZipFile
    ) -> list[str]:
        """
        Inspect single ZIP entry for security threats.

        Args:
            entry: ZIP entry metadata.
            zip_file: Parent ZIP archive.

        Returns:
            List of threat descriptions.
        """
        threats = []
        filename = entry.filename

        # 1. Check for directory traversal attacks
        if self._has_directory_traversal(filename):
            threats.append(f"Directory traversal attack in '{filename}'")

        # 2. Check for absolute paths
        if not self.config.limits.allow_absolute_paths and self._has_absolute_path(
            filename
        ):
            threats.append(f"Absolute path detected in '{filename}'")

        # 3. Check for symbolic links
        if not self.config.limits.allow_symlinks and self._is_symlink(entry):
            threats.append(f"Symbolic link detected: '{filename}'")

        # 4. Check filename length limits
        if len(os.path.basename(filename)) > self.config.limits.max_filename_length:
            threats.append(
                f"Filename too long: '{filename}' ({len(os.path.basename(filename))} chars)"
            )

        # 5. Check path length limits
        if len(filename) > self.config.limits.max_path_length:
            threats.append(f"Path too long: '{filename}' ({len(filename)} chars)")

        # 6. Check for suspicious filename patterns
        suspicious_patterns = self._check_suspicious_patterns(filename)
        threats.extend(suspicious_patterns)

        # 7. Check for nested archives
        if not self.config.limits.allow_nested_archives and self._is_nested_archive(
            filename
        ):
            threats.append(f"Nested archive detected: '{filename}'")

        # 8. Check file content if enabled and entry is small enough
        if (
            self.config.limits.scan_zip_content
            and not entry.is_dir()
            and entry.file_size < 1024 * 1024
        ):  # 1MB limit for content scan
            content_threats = self._inspect_entry_content(entry, zip_file)
            threats.extend(content_threats)

        return threats

    def _inspect_zip_structure(self, entries: list[zipfile.ZipInfo]) -> list[str]:
        """
        Inspect ZIP structure for anomalies.

        Args:
            entries: All ZIP entries to analyze.

        Returns:
            List of structural threat descriptions.
        """
        threats = []

        # Check directory depth
        max_depth = 0
        for entry in entries:
            depth = entry.filename.count("/") + entry.filename.count("\\")
            max_depth = max(max_depth, depth)

        if max_depth > self.config.limits.max_zip_depth:
            threats.append(
                f"Excessive directory depth: {max_depth} (max: {self.config.limits.max_zip_depth})"
            )

        # Check for suspicious file distribution
        file_types = {}
        for entry in entries:
            if not entry.is_dir():
                ext = os.path.splitext(entry.filename)[1].lower()
                file_types[ext] = file_types.get(ext, 0) + 1

        # Check for excessive number of same-type files (potential spam/bomb)
        for ext, count in file_types.items():
            if count > self.config.limits.max_number_files_same_type:
                threats.append(
                    f"Excessive number of {ext} files: {self.config.limits.max_number_files_same_type}"
                )

        return threats

    def _has_directory_traversal(self, filename: str) -> bool:
        """
        Check for directory traversal indicators.

        Args:
            filename: Filename to check.

        Returns:
            True if traversal detected.
        """
        filename_lower = filename.lower()

        for category in SuspiciousFilePattern:
            if category == SuspiciousFilePattern.DIRECTORY_TRAVERSAL:
                for pattern in category.value:
                    if pattern.lower() in filename_lower:
                        return True

        # Additional checks for normalized paths
        normalized = os.path.normpath(filename)
        if normalized.startswith("..") or "/.." in normalized or "\\.." in normalized:
            return True

        return False

    def _has_absolute_path(self, filename: str) -> bool:
        """
        Check if filename is an absolute path.

        Args:
            filename: Path to check.

        Returns:
            True if absolute path detected.
        """
        return (
            filename.startswith("/")  # Unix absolute path
            or filename.startswith("\\")  # Windows UNC path
            or (len(filename) > 1 and filename[1] == ":")  # Windows drive path
        )

    def _is_symlink(self, entry: zipfile.ZipInfo) -> bool:
        """
        Check if entry is a symbolic link.

        Args:
            entry: ZIP entry to check.

        Returns:
            True if entry is a symlink.
        """
        # Check if entry has symlink attributes
        return (entry.external_attr >> 16) & 0o120000 == 0o120000

    def _check_suspicious_patterns(self, filename: str) -> list[str]:
        """
        Check filename for suspicious patterns.

        Args:
            filename: Filename to check.

        Returns:
            List of pattern warnings.
        """
        threats = []
        filename_lower = filename.lower()
        basename = os.path.basename(filename_lower)

        # Check suspicious names
        for pattern in SuspiciousFilePattern.SUSPICIOUS_NAMES.value:
            if basename == pattern.lower():
                threats.append(f"Suspicious filename pattern: '{filename}'")
                break

        # Check suspicious path components
        for pattern in SuspiciousFilePattern.SUSPICIOUS_PATHS.value:
            if pattern.lower() in filename_lower:
                threats.append(
                    f"Suspicious path component: '{filename}' contains '{pattern}'"
                )
                break

        return threats

    def _is_nested_archive(self, filename: str) -> bool:
        """
        Check if filename represents a nested archive.

        Args:
            filename: Filename to check.

        Returns:
            True if nested archive detected.
        """
        ext = os.path.splitext(filename)[1].lower()

        for category in ZipThreatCategory:
            if category == ZipThreatCategory.NESTED_ARCHIVES:
                return ext in category.value

        return False

    def _inspect_entry_content(
        self, entry: zipfile.ZipInfo, zip_file: zipfile.ZipFile
    ) -> list[str]:
        """
        Inspect ZIP entry content for malicious signatures.

        Args:
            entry: ZIP entry to inspect.
            zip_file: Parent ZIP archive.

        Returns:
            List of content threat descriptions.
        """
        threats = []

        try:
            # Read first few bytes to check for executable signatures
            with zip_file.open(entry, "r") as file:
                content_sample = file.read(512)  # Read first 512 bytes

                # Check for executable signatures
                for signature in SuspiciousFilePattern.EXECUTABLE_SIGNATURES.value:
                    if content_sample.startswith(signature):
                        threats.append(
                            f"Executable content detected in '{entry.filename}'"
                        )
                        break

                binary_exts = set()
                for category in BinaryFileCategory:
                    binary_exts.update(category.value)

                ext = os.path.splitext(entry.filename)[1].lower()
                if ext not in binary_exts:
                    # Check for script content patterns
                    if self._contains_script_patterns(content_sample, entry.filename):
                        threats.append(f"Script content detected in '{entry.filename}'")

        except Exception as err:
            logger.warning(
                "Could not inspect content of '%s': %s",
                entry.filename,
                err,
            )

        return threats

    def _contains_script_patterns(self, content: bytes, filename: str) -> bool:
        """
        Check content for malicious script patterns.

        Args:
            content: Raw bytes to inspect.
            filename: Filename for context.

        Returns:
            True if script patterns found.
        """
        try:
            # Try to decode as text
            text_content = content.decode("utf-8", errors="ignore").lower()

            # Check for common script patterns
            script_patterns = [
                "#!/bin/",
                "#!/usr/bin/",
                "powershell",
                "cmd.exe",
                "eval(",
                "exec(",
                "system(",
                "shell_exec(",
                "<script",
                "<?php",
                "<%",
                "import os",
                "import subprocess",
            ]

            for pattern in script_patterns:
                if pattern in text_content:
                    return True

        except Exception:
            # If we can't decode as text, it's probably binary
            pass

        return False
