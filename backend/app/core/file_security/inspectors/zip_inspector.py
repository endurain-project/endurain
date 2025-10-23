"""
ZIP Content Inspector Module

Handles deep inspection of ZIP file contents for security threats.
"""
import io
import os
import time
import zipfile
from typing import List, Tuple, TYPE_CHECKING

import core.logger as core_logger
from ..enums import SuspiciousFilePattern, ZipThreatCategory

if TYPE_CHECKING:
    from ..config import FileSecurityConfig


class ZipContentInspector:

    def __init__(self, config: "FileSecurityConfig"):
        self.config = config

    def inspect_zip_content(self, file_content: bytes) -> Tuple[bool, str]:
        """
        Perform deep inspection of ZIP file contents.
        
        Args:
            file_content: The ZIP file content as bytes
            
        Returns:
            Tuple[bool, str]: (is_safe, error_message)
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
                    if time.time() - start_time > self.config.limits.zip_analysis_timeout:
                        return False, f"ZIP content inspection timeout after {self.config.limits.zip_analysis_timeout}s"
                    
                    # Inspect individual entry
                    entry_threats = self._inspect_zip_entry(entry, zip_file)
                    threats_found.extend(entry_threats)
                
                # Check for ZIP structure threats
                structure_threats = self._inspect_zip_structure(zip_entries)
                threats_found.extend(structure_threats)
                
                # Return results
                if threats_found:
                    return False, f"ZIP content threats detected: {'; '.join(threats_found)}"
                
                core_logger.print_to_log(
                    f"ZIP content inspection passed: {len(zip_entries)} entries analyzed",
                    "debug"
                )
                return True, "ZIP content inspection passed"
                
        except zipfile.BadZipFile:
            return False, "Invalid or corrupted ZIP file structure"
        except Exception as err:
            core_logger.print_to_log(
                f"Error during ZIP content inspection: {err}", "warning", exc=err
            )
            return False, f"ZIP content inspection failed: {str(err)}"

    def _inspect_zip_entry(self, entry: zipfile.ZipInfo, zip_file: zipfile.ZipFile) -> List[str]:
        """
        Inspect individual ZIP entry for threats.
        
        Args:
            entry: The ZIP entry to inspect
            zip_file: The ZIP file object
            
        Returns:
            List[str]: List of threats found
        """
        threats = []
        filename = entry.filename
        
        # 1. Check for directory traversal attacks
        if self._has_directory_traversal(filename):
            threats.append(f"Directory traversal attack in '{filename}'")
        
        # 2. Check for absolute paths
        if not self.config.limits.allow_absolute_paths and self._has_absolute_path(filename):
            threats.append(f"Absolute path detected in '{filename}'")
        
        # 3. Check for symbolic links
        if not self.config.limits.allow_symlinks and self._is_symlink(entry):
            threats.append(f"Symbolic link detected: '{filename}'")
        
        # 4. Check filename length limits
        if len(os.path.basename(filename)) > self.config.limits.max_filename_length:
            threats.append(f"Filename too long: '{filename}' ({len(os.path.basename(filename))} chars)")
        
        # 5. Check path length limits
        if len(filename) > self.config.limits.max_path_length:
            threats.append(f"Path too long: '{filename}' ({len(filename)} chars)")
        
        # 6. Check for suspicious filename patterns
        suspicious_patterns = self._check_suspicious_patterns(filename)
        threats.extend(suspicious_patterns)
        
        # 7. Check for nested archives
        if not self.config.limits.allow_nested_archives and self._is_nested_archive(filename):
            threats.append(f"Nested archive detected: '{filename}'")
        
        # 8. Check file content if enabled and entry is small enough
        if self.config.limits.scan_zip_content and not entry.is_dir() and entry.file_size < 1024 * 1024:  # 1MB limit for content scan
            content_threats = self._inspect_entry_content(entry, zip_file)
            threats.extend(content_threats)
        
        return threats

    def _inspect_zip_structure(self, entries: List[zipfile.ZipInfo]) -> List[str]:
        """
        Inspect overall ZIP structure for threats.
        
        Args:
            entries: List of ZIP entries
            
        Returns:
            List[str]: List of structural threats found
        """
        threats = []
        
        # Check directory depth
        max_depth = 0
        for entry in entries:
            depth = entry.filename.count('/') + entry.filename.count('\\')
            max_depth = max(max_depth, depth)
        
        if max_depth > self.config.limits.max_zip_depth:
            threats.append(f"Excessive directory depth: {max_depth} (max: {self.config.limits.max_zip_depth})")
        
        # Check for suspicious file distribution
        file_types = {}
        for entry in entries:
            if not entry.is_dir():
                ext = os.path.splitext(entry.filename)[1].lower()
                file_types[ext] = file_types.get(ext, 0) + 1
        
        # Check for excessive number of same-type files (potential spam/bomb)
        for ext, count in file_types.items():
            if count > 1000:  # More than 1000 files of same type
                threats.append(f"Excessive number of {ext} files: {count}")
        
        return threats

    def _has_directory_traversal(self, filename: str) -> bool:
        """Check if filename contains directory traversal patterns."""
        filename_lower = filename.lower()
        
        for category in SuspiciousFilePattern:
            if category == SuspiciousFilePattern.DIRECTORY_TRAVERSAL:
                for pattern in category.value:
                    if pattern.lower() in filename_lower:
                        return True
        
        # Additional checks for normalized paths
        normalized = os.path.normpath(filename)
        if normalized.startswith('..') or '/..' in normalized or '\\..' in normalized:
            return True
        
        return False

    def _has_absolute_path(self, filename: str) -> bool:
        """Check if filename is an absolute path."""
        return (
            filename.startswith('/') or  # Unix absolute path
            filename.startswith('\\') or  # Windows UNC path
            (len(filename) > 1 and filename[1] == ':')  # Windows drive path
        )

    def _is_symlink(self, entry: zipfile.ZipInfo) -> bool:
        """Check if ZIP entry is a symbolic link."""
        # Check if entry has symlink attributes
        return (entry.external_attr >> 16) & 0o120000 == 0o120000

    def _check_suspicious_patterns(self, filename: str) -> List[str]:
        """Check filename for suspicious patterns."""
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
                threats.append(f"Suspicious path component: '{filename}' contains '{pattern}'")
                break
        
        return threats

    def _is_nested_archive(self, filename: str) -> bool:
        """Check if filename is a nested archive."""
        ext = os.path.splitext(filename)[1].lower()
        
        for category in ZipThreatCategory:
            if category == ZipThreatCategory.NESTED_ARCHIVES:
                return ext in category.value
        
        return False

    def _inspect_entry_content(self, entry: zipfile.ZipInfo, zip_file: zipfile.ZipFile) -> List[str]:
        """
        Inspect the content of a ZIP entry for threats.
        
        Args:
            entry: The ZIP entry to inspect
            zip_file: The ZIP file object
            
        Returns:
            List[str]: List of content threats found
        """
        threats = []
        
        try:
            # Read first few bytes to check for executable signatures
            with zip_file.open(entry, 'r') as file:
                content_sample = file.read(512)  # Read first 512 bytes
                
                # Check for executable signatures
                for signature in SuspiciousFilePattern.EXECUTABLE_SIGNATURES.value:
                    if content_sample.startswith(signature):
                        threats.append(f"Executable content detected in '{entry.filename}'")
                        break
                
                # Check for script content patterns
                if self._contains_script_patterns(content_sample, entry.filename):
                    threats.append(f"Script content detected in '{entry.filename}'")
        
        except Exception as err:
            core_logger.print_to_log(
                f"Warning: Could not inspect content of '{entry.filename}': {err}",
                "warning"
            )
        
        return threats

    def _contains_script_patterns(self, content: bytes, filename: str) -> bool:
        """Check if content contains script patterns."""
        try:
            # Try to decode as text
            text_content = content.decode('utf-8', errors='ignore').lower()
            
            # Check for common script patterns
            script_patterns = [
                '#!/bin/', '#!/usr/bin/', 'powershell', 'cmd.exe',
                'eval(', 'exec(', 'system(', 'shell_exec(',
                '<script', '<?php', '<%', 'import os', 'import subprocess'
            ]
            
            for pattern in script_patterns:
                if pattern in text_content:
                    return True
            
        except Exception:
            # If we can't decode as text, it's probably binary
            pass
        
        return False