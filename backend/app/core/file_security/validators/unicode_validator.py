"""
Unicode Security Validator Module

Handles validation of Unicode-based attacks in filenames.
"""
import unicodedata
from typing import TYPE_CHECKING

import core.logger as core_logger
from .base import BaseValidator

if TYPE_CHECKING:
    from ..config import FileSecurityConfig


class UnicodeSecurityValidator(BaseValidator):
    
    def __init__(self, config: "FileSecurityConfig"):
        super().__init__(config)

    def validate_unicode_security(self, filename: str) -> str:
        """
        Validate and normalize Unicode characters in filenames.
        
        Args:
            filename: The filename to validate and normalize
            
        Returns:
            str: The normalized filename
            
        Raises:
            ValueError: If dangerous Unicode characters are detected
        """
        if not filename:
            return filename

        # Check for dangerous Unicode characters
        dangerous_chars_found = []
        for i, char in enumerate(filename):
            char_code = ord(char)
            if char_code in self.config.DANGEROUS_UNICODE_CHARS:
                dangerous_chars_found.append((char, char_code, i))

        # If dangerous characters found, reject the file entirely
        if dangerous_chars_found:
            char_details = []
            for char, code, pos in dangerous_chars_found:
                char_name = unicodedata.name(char, f"U+{code:04X}")
                char_details.append(
                    f"'{char}' (U+{code:04X}: {char_name}) at position {pos}"
                )

            raise ValueError(
                f"Dangerous Unicode characters detected in filename: {', '.join(char_details)}. "
                f"These characters can be used to disguise file extensions or create security vulnerabilities."
            )

        # Normalize Unicode to prevent normalization attacks
        # Use NFC (Canonical Decomposition, followed by Canonical Composition)
        # This prevents attacks where different Unicode representations of the same text are used
        normalized_filename = unicodedata.normalize("NFC", filename)

        # Check if normalization changed the filename significantly
        if normalized_filename != filename:
            core_logger.print_to_log(
                f"Unicode normalization applied: '{filename}' -> '{normalized_filename}'",
                "info",
            )

        # Additional check: ensure normalized filename doesn't contain dangerous chars
        # (some normalization attacks might introduce them)
        for char in normalized_filename:
            char_code = ord(char)
            if char_code in self.config.DANGEROUS_UNICODE_CHARS:
                raise ValueError(
                    f"Unicode normalization resulted in dangerous character: "
                    f"'{char}' (U+{char_code:04X}: {unicodedata.name(char, f'U+{char_code:04X}')})"
                )

        return normalized_filename
    
    def validate(self, filename: str) -> str:
        """Compatibility method for base class interface."""
        return self.validate_unicode_security(filename)