"""
File security configuration module.
"""

from dataclasses import dataclass

import logging
from .enums import (
    DangerousExtensionCategory,
    CompoundExtensionCategory,
    UnicodeAttackCategory,
)
from .exceptions import ConfigValidationError, FileSecurityConfigurationError


logger = logging.getLogger(__name__)


@dataclass
class SecurityLimits:
    """
    Security constraints for file submissions.

    Attributes:
        max_image_size: Maximum size in bytes for image files.
        max_zip_size: Maximum size in bytes for ZIP archives.
        max_compression_ratio: Maximum expansion ratio for ZIP files.
        max_uncompressed_size: Maximum cumulative size of ZIP contents.
        max_individual_file_size: Maximum size of single file in ZIP.
        max_zip_entries: Maximum number of file entries in ZIP.
        zip_analysis_timeout: Maximum seconds for ZIP analysis.
        max_zip_depth: Maximum directory nesting depth in ZIP.
        max_filename_length: Maximum length for filenames in ZIP.
        max_path_length: Maximum length for full paths in ZIP.
        allow_nested_archives: Whether nested archives are permitted.
        allow_symlinks: Whether symbolic links are permitted.
        allow_absolute_paths: Whether absolute paths are permitted.
        scan_zip_content: Whether deep content inspection is enabled.
    """

    # File size limits (in bytes)
    max_image_size: int = 20 * 1024 * 1024  # 20MB for images
    max_zip_size: int = 500 * 1024 * 1024  # 500MB for ZIP files

    # ZIP compression security settings
    max_compression_ratio: int = 100  # Maximum allowed expansion ratio (e.g., 100:1)
    max_uncompressed_size: int = 1024 * 1024 * 1024  # 1GB max uncompressed size
    max_individual_file_size: int = (
        500 * 1024 * 1024
    )  # 500MB max per individual file in ZIP
    max_zip_entries: int = 10000  # Maximum number of files in ZIP archive
    zip_analysis_timeout: float = (
        5.0  # Maximum seconds to spend analyzing ZIP structure
    )

    # ZIP content inspection settings
    max_zip_depth: int = 10  # Maximum nesting depth for directories in ZIP
    max_filename_length: int = 255  # Maximum length for individual file names
    max_path_length: int = 1024  # Maximum length for full file paths
    max_number_files_same_type: int = 1000  # Maximum number of files of the same type
    allow_nested_archives: bool = False  # Whether to allow nested archive files
    allow_symlinks: bool = False  # Whether to allow symbolic links in ZIP
    allow_absolute_paths: bool = False  # Whether to allow absolute paths in ZIP
    scan_zip_content: bool = True  # Whether to perform deep content inspection


class FileSecurityConfig:
    """
    Centralizes file upload security settings and validation.

    Attributes:
        limits: Security limits configuration instance.
        ALLOWED_IMAGE_MIMES: Permitted MIME types for images.
        ALLOWED_ZIP_MIMES: Permitted MIME types for ZIP files.
        ALLOWED_IMAGE_EXTENSIONS: Permitted image file extensions.
        ALLOWED_ZIP_EXTENSIONS: Permitted ZIP file extensions.
        BLOCKED_EXTENSIONS: Dangerous file extensions to block.
        COMPOUND_BLOCKED_EXTENSIONS: Multi-part extensions to block.
        DANGEROUS_UNICODE_CHARS: Unicode characters for filename attacks.
        WINDOWS_RESERVED_NAMES: Platform-specific reserved filenames.
    """

    # Security limits configuration
    limits = SecurityLimits()

    # Allowed MIME types for images
    ALLOWED_IMAGE_MIMES: set[str] = {"image/jpeg", "image/jpg", "image/png"}

    # Allowed MIME types for ZIP files
    ALLOWED_ZIP_MIMES: set[str] = {
        "application/zip",
        "application/x-zip-compressed",
        "multipart/x-zip",
    }

    # Allowed file extensions
    ALLOWED_IMAGE_EXTENSIONS: set[str] = {".jpg", ".jpeg", ".png"}
    ALLOWED_ZIP_EXTENSIONS: set[str] = {".zip"}

    # Generate dangerous file extensions from categorized enums
    @staticmethod
    def _generate_blocked_extensions() -> set[str]:
        """
        Aggregate all dangerous extension categories.

        Returns:
            Combined set of blocked file extensions.
        """
        blocked_extensions = set()

        # Combine all dangerous extension categories
        for category in DangerousExtensionCategory:
            blocked_extensions.update(category.value)

        return blocked_extensions

    # Generate compound dangerous file extensions from categorized enums
    @staticmethod
    def _generate_compound_blocked_extensions() -> set[str]:
        """
        Aggregate all compound extension categories.

        Returns:
            Combined set of blocked compound file extensions.
        """
        compound_extensions = set()

        # Combine all compound extension categories
        for category in CompoundExtensionCategory:
            compound_extensions.update(category.value)

        return compound_extensions

    # Generate dangerous Unicode characters from categorized enums
    @staticmethod
    def _generate_dangerous_unicode_chars() -> set[int]:
        """
        Aggregate all dangerous Unicode code points.

        Returns:
            Combined set of dangerous Unicode code points.
        """
        dangerous_chars = set()

        # Combine all Unicode attack categories
        for category in UnicodeAttackCategory:
            dangerous_chars.update(category.value)

        return dangerous_chars

    # Dangerous file extensions to explicitly block (generated from enums)
    BLOCKED_EXTENSIONS: set[str] = _generate_blocked_extensions()

    # Compound dangerous file extensions (multi-part extensions)
    # These are checked as complete strings, not individual parts
    COMPOUND_BLOCKED_EXTENSIONS: set[str] = _generate_compound_blocked_extensions()

    # Dangerous Unicode characters that can be used for filename attacks
    # These characters can disguise file extensions or cause rendering issues
    DANGEROUS_UNICODE_CHARS: set[int] = _generate_dangerous_unicode_chars()

    # Windows reserved names that cannot be used as filenames
    # These names are reserved by Windows regardless of extension
    WINDOWS_RESERVED_NAMES: set[str] = {
        "con",
        "prn",
        "aux",
        "nul",
        "com1",
        "com2",
        "com3",
        "com4",
        "com5",
        "com6",
        "com7",
        "com8",
        "com9",
        "lpt1",
        "lpt2",
        "lpt3",
        "lpt4",
        "lpt5",
        "lpt6",
        "lpt7",
        "lpt8",
        "lpt9",
    }

    # Configuration validation trigger
    @classmethod
    def __init_subclass__(cls, **kwargs):
        """
        Hook for subclass creation to validate configuration.

        Args:
            **kwargs: Subclass initialization arguments.
        """
        super().__init_subclass__(**kwargs)
        # Perform validation with warnings allowed (non-strict mode)
        try:
            cls.validate_and_report(strict=False)
        except Exception as err:
            logger.warning("Configuration validation failed: %s", err)

    @classmethod
    def get_extensions_by_category(
        cls, category: DangerousExtensionCategory
    ) -> set[str]:
        """
        Return extensions for a dangerous extension category.

        Args:
            category: The dangerous extension category.

        Returns:
            Copy of extensions in the specified category.
        """
        return category.value.copy()

    @classmethod
    def get_compound_extensions_by_category(
        cls, category: CompoundExtensionCategory
    ) -> set[str]:
        """
        Return compound extensions for a category.

        Args:
            category: The compound extension category.

        Returns:
            Copy of compound extensions in the specified category.
        """
        return category.value.copy()

    @classmethod
    def get_unicode_chars_by_category(cls, category: UnicodeAttackCategory) -> set[int]:
        """
        Return Unicode code points for an attack category.

        Args:
            category: The Unicode attack category.

        Returns:
            Copy of code points in the specified category.
        """
        return category.value.copy()

    @classmethod
    def is_extension_in_category(
        cls, extension: str, category: DangerousExtensionCategory
    ) -> bool:
        """
        Check if extension belongs to a dangerous category.

        Args:
            extension: File extension to evaluate.
            category: Category to check against.

        Returns:
            True if extension is in the category, False otherwise.
        """
        return extension.lower() in category.value

    @classmethod
    def get_extension_category(
        cls, extension: str
    ) -> DangerousExtensionCategory | None:
        """
        Return the dangerous extension category for an extension.

        Args:
            extension: The file extension to evaluate.

        Returns:
            Matching category if dangerous, None otherwise.
        """
        extension_lower = extension.lower()
        for category in DangerousExtensionCategory:
            if extension_lower in category.value:
                return category
        return None

    @classmethod
    def validate_configuration(cls, strict: bool = True) -> list[ConfigValidationError]:
        """
        Run all configuration validation routines.

        Args:
            strict: Reserved for future behavior adjustments.

        Returns:
            List of detected validation errors.
        """
        errors = []

        # Validate file size limits
        errors.extend(cls._validate_file_size_limits())

        # Validate MIME type configurations
        errors.extend(cls._validate_mime_configurations())

        # Validate file extension configurations
        errors.extend(cls._validate_extension_configurations())

        # Validate ZIP compression settings
        errors.extend(cls._validate_compression_settings())

        # Validate enum consistency
        errors.extend(cls._validate_enum_consistency())

        # Validate cross-configuration dependencies
        errors.extend(cls._validate_cross_dependencies())

        return errors

    @classmethod
    def _validate_file_size_limits(cls) -> list[ConfigValidationError]:
        """
        Validate configured file size limits.

        Returns:
            List of detected configuration issues.
        """
        errors = []

        # Check image size limits
        if cls.limits.max_image_size <= 0:
            errors.append(
                ConfigValidationError(
                    error_type="invalid_size_limit",
                    message="max_image_size must be greater than 0",
                    severity="error",
                    component="file_sizes",
                    recommendation="Set max_image_size to a positive value (e.g., 20MB)",
                )
            )

        if cls.limits.max_image_size > 100 * 1024 * 1024:  # 100MB
            errors.append(
                ConfigValidationError(
                    error_type="excessive_size_limit",
                    message=f"max_image_size ({cls.limits.max_image_size // (1024*1024)}MB) is very large",
                    severity="warning",
                    component="file_sizes",
                    recommendation="Consider reducing image size limit to prevent resource exhaustion",
                )
            )

        # Check ZIP size limits
        if cls.limits.max_zip_size <= 0:
            errors.append(
                ConfigValidationError(
                    error_type="invalid_size_limit",
                    message="max_zip_size must be greater than 0",
                    severity="error",
                    component="file_sizes",
                    recommendation="Set max_zip_size to a positive value (e.g., 500MB)",
                )
            )

        if cls.limits.max_zip_size > 2 * 1024 * 1024 * 1024:  # 2GB
            errors.append(
                ConfigValidationError(
                    error_type="excessive_size_limit",
                    message=f"max_zip_size ({cls.limits.max_zip_size // (1024*1024)}MB) is very large",
                    severity="warning",
                    component="file_sizes",
                    recommendation="Consider reducing ZIP size limit to prevent resource exhaustion",
                )
            )

        # Validate size relationship
        if cls.limits.max_zip_size <= cls.limits.max_image_size:
            errors.append(
                ConfigValidationError(
                    error_type="inconsistent_size_limits",
                    message="max_zip_size should typically be larger than max_image_size",
                    severity="warning",
                    component="file_sizes",
                    recommendation="ZIP files usually contain multiple files and should have higher limits",
                )
            )

        return errors

    @classmethod
    def _validate_mime_configurations(cls) -> list[ConfigValidationError]:
        """
        Validate MIME type configurations.

        Returns:
            List of detected configuration issues.
        """
        errors = []

        # Check image MIME types
        if not cls.ALLOWED_IMAGE_MIMES:
            errors.append(
                ConfigValidationError(
                    error_type="empty_mime_set",
                    message="ALLOWED_IMAGE_MIMES cannot be empty",
                    severity="error",
                    component="mime_types",
                    recommendation="Add at least one allowed image MIME type",
                )
            )

        # Validate image MIME type format
        for mime_type in cls.ALLOWED_IMAGE_MIMES:
            if not mime_type.startswith("image/"):
                errors.append(
                    ConfigValidationError(
                        error_type="invalid_image_mime",
                        message=f"Image MIME type '{mime_type}' should start with 'image/'",
                        severity="warning",
                        component="mime_types",
                        recommendation="Use standard image MIME types like 'image/jpeg', 'image/png'",
                    )
                )

        # Check ZIP MIME types
        if not cls.ALLOWED_ZIP_MIMES:
            errors.append(
                ConfigValidationError(
                    error_type="empty_mime_set",
                    message="ALLOWED_ZIP_MIMES cannot be empty",
                    severity="error",
                    component="mime_types",
                    recommendation="Add at least one allowed ZIP MIME type",
                )
            )

        # Check for duplicate MIME types
        all_mimes = list(cls.ALLOWED_IMAGE_MIMES) + list(cls.ALLOWED_ZIP_MIMES)
        duplicates = set([mime for mime in all_mimes if all_mimes.count(mime) > 1])
        if duplicates:
            errors.append(
                ConfigValidationError(
                    error_type="duplicate_mime_types",
                    message=f"Duplicate MIME types found: {duplicates}",
                    severity="warning",
                    component="mime_types",
                    recommendation="Remove duplicate MIME types to avoid confusion",
                )
            )

        return errors

    @classmethod
    def _validate_extension_configurations(cls) -> list[ConfigValidationError]:
        """
        Validate file extension configurations.

        Returns:
            List of detected configuration issues.
        """
        errors = []

        # Check extension format
        for ext_set_name, ext_set in [
            ("ALLOWED_IMAGE_EXTENSIONS", cls.ALLOWED_IMAGE_EXTENSIONS),
            ("ALLOWED_ZIP_EXTENSIONS", cls.ALLOWED_ZIP_EXTENSIONS),
        ]:
            if not ext_set:
                errors.append(
                    ConfigValidationError(
                        error_type="empty_extension_set",
                        message=f"{ext_set_name} cannot be empty",
                        severity="error",
                        component="extensions",
                        recommendation=f"Add at least one extension to {ext_set_name}",
                    )
                )

            for ext in ext_set:
                if not ext.startswith("."):
                    errors.append(
                        ConfigValidationError(
                            error_type="invalid_extension_format",
                            message=f"Extension '{ext}' in {ext_set_name} should start with '.'",
                            severity="error",
                            component="extensions",
                            recommendation="Use format '.ext' for file extensions",
                        )
                    )

        # Check blocked extensions
        if not cls.BLOCKED_EXTENSIONS:
            errors.append(
                ConfigValidationError(
                    error_type="empty_blocked_extensions",
                    message="BLOCKED_EXTENSIONS is empty - security risk",
                    severity="error",
                    component="extensions",
                    recommendation="Ensure dangerous extensions are properly blocked",
                )
            )

        # Check for overlap between allowed and blocked extensions
        image_blocked = cls.ALLOWED_IMAGE_EXTENSIONS.intersection(
            cls.BLOCKED_EXTENSIONS
        )
        if image_blocked:
            errors.append(
                ConfigValidationError(
                    error_type="extension_conflict",
                    message=f"Image extensions {image_blocked} are both allowed and blocked",
                    severity="error",
                    component="extensions",
                    recommendation="Remove conflicts between allowed and blocked extensions",
                )
            )

        zip_blocked = cls.ALLOWED_ZIP_EXTENSIONS.intersection(cls.BLOCKED_EXTENSIONS)
        if zip_blocked:
            errors.append(
                ConfigValidationError(
                    error_type="extension_conflict",
                    message=f"ZIP extensions {zip_blocked} are both allowed and blocked",
                    severity="error",
                    component="extensions",
                    recommendation="Remove conflicts between allowed and blocked extensions",
                )
            )

        # Check compound extension consistency
        compound_overlap = cls.BLOCKED_EXTENSIONS.intersection(
            cls.COMPOUND_BLOCKED_EXTENSIONS
        )
        if compound_overlap:
            errors.append(
                ConfigValidationError(
                    error_type="compound_extension_overlap",
                    message=f"Extensions {compound_overlap} appear in both blocked and compound blocked lists",
                    severity="warning",
                    component="extensions",
                    recommendation="Compound extensions should only be in COMPOUND_BLOCKED_EXTENSIONS",
                )
            )

        return errors

    @classmethod
    def _validate_compression_settings(cls) -> list[ConfigValidationError]:
        """
        Validate compression-related limits.

        Returns:
            List of detected configuration issues.
        """
        errors = []

        # Validate compression ratio
        if cls.limits.max_compression_ratio <= 0:
            errors.append(
                ConfigValidationError(
                    error_type="invalid_compression_ratio",
                    message="max_compression_ratio must be greater than 0",
                    severity="error",
                    component="compression",
                    recommendation="Set a reasonable compression ratio limit (e.g., 100:1)",
                )
            )

        if cls.limits.max_compression_ratio < 10:
            errors.append(
                ConfigValidationError(
                    error_type="too_strict_compression",
                    message=f"max_compression_ratio ({cls.limits.max_compression_ratio}) is very strict",
                    severity="warning",
                    component="compression",
                    recommendation="Consider allowing higher compression ratios for legitimate files",
                )
            )

        if cls.limits.max_compression_ratio > 1000:
            errors.append(
                ConfigValidationError(
                    error_type="too_permissive_compression",
                    message=f"max_compression_ratio ({cls.limits.max_compression_ratio}) may allow zip bombs",
                    severity="warning",
                    component="compression",
                    recommendation="Reduce compression ratio limit to prevent zip bomb attacks",
                )
            )

        # Validate uncompressed size limit
        if cls.limits.max_uncompressed_size <= 0:
            errors.append(
                ConfigValidationError(
                    error_type="invalid_uncompressed_size",
                    message="max_uncompressed_size must be greater than 0",
                    severity="error",
                    component="compression",
                    recommendation="Set a reasonable uncompressed size limit",
                )
            )

        # Validate individual file size limit
        if cls.limits.max_individual_file_size <= 0:
            errors.append(
                ConfigValidationError(
                    error_type="invalid_individual_file_size",
                    message="max_individual_file_size must be greater than 0",
                    severity="error",
                    component="compression",
                    recommendation="Set a reasonable individual file size limit",
                )
            )

        # Check individual file size doesn't exceed total uncompressed size
        if cls.limits.max_individual_file_size > cls.limits.max_uncompressed_size:
            errors.append(
                ConfigValidationError(
                    error_type="inconsistent_size_limits",
                    message=f"max_individual_file_size ({cls.limits.max_individual_file_size // (1024*1024)}MB) "
                    f"exceeds max_uncompressed_size ({cls.limits.max_uncompressed_size // (1024*1024)}MB)",
                    severity="warning",
                    component="compression",
                    recommendation="Individual file size limit should not exceed total uncompressed size limit",
                )
            )

        # Validate ZIP entry limits
        if cls.limits.max_zip_entries <= 0:
            errors.append(
                ConfigValidationError(
                    error_type="invalid_zip_entries",
                    message="max_zip_entries must be greater than 0",
                    severity="error",
                    component="compression",
                    recommendation="Set a reasonable limit for ZIP file entries",
                )
            )

        if cls.limits.max_zip_entries > 100000:
            errors.append(
                ConfigValidationError(
                    error_type="excessive_zip_entries",
                    message=f"max_zip_entries ({cls.limits.max_zip_entries}) is very high",
                    severity="warning",
                    component="compression",
                    recommendation="High entry limits may impact performance",
                )
            )

        # Validate timeout settings
        if cls.limits.zip_analysis_timeout <= 0:
            errors.append(
                ConfigValidationError(
                    error_type="invalid_timeout",
                    message="zip_analysis_timeout must be greater than 0",
                    severity="error",
                    component="compression",
                    recommendation="Set a reasonable timeout for ZIP analysis",
                )
            )

        if cls.limits.zip_analysis_timeout > 30:
            errors.append(
                ConfigValidationError(
                    error_type="excessive_timeout",
                    message=f"zip_analysis_timeout ({cls.limits.zip_analysis_timeout}s) is very long",
                    severity="warning",
                    component="compression",
                    recommendation="Long timeouts may impact user experience",
                )
            )

        return errors

    @classmethod
    def _validate_enum_consistency(cls) -> list[ConfigValidationError]:
        """
        Validate enum categories for emptiness and overlaps.

        Returns:
            List of detected configuration issues.
        """
        errors = []

        # Check for empty enum categories
        for category in DangerousExtensionCategory:
            if not category.value:
                errors.append(
                    ConfigValidationError(
                        error_type="empty_enum_category",
                        message=f"Extension category {category.name} is empty",
                        severity="warning",
                        component="enums",
                        recommendation=f"Add extensions to {category.name} or remove unused category",
                    )
                )

        for category in CompoundExtensionCategory:
            if not category.value:
                errors.append(
                    ConfigValidationError(
                        error_type="empty_enum_category",
                        message=f"Compound extension category {category.name} is empty",
                        severity="warning",
                        component="enums",
                        recommendation=f"Add extensions to {category.name} or remove unused category",
                    )
                )

        for category in UnicodeAttackCategory:
            if not category.value:
                errors.append(
                    ConfigValidationError(
                        error_type="empty_enum_category",
                        message=f"Unicode attack category {category.name} is empty",
                        severity="warning",
                        component="enums",
                        recommendation=f"Add Unicode characters to {category.name} or remove unused category",
                    )
                )

        # Check for overlapping extensions between categories
        all_extensions_by_category = {}
        for category in DangerousExtensionCategory:
            all_extensions_by_category[category.name] = category.value

        for cat1_name, cat1_exts in all_extensions_by_category.items():
            for cat2_name, cat2_exts in all_extensions_by_category.items():
                if cat1_name != cat2_name:
                    overlap = cat1_exts.intersection(cat2_exts)
                    if overlap:
                        errors.append(
                            ConfigValidationError(
                                error_type="category_overlap",
                                message=f"Categories {cat1_name} and {cat2_name} share extensions: {overlap}",
                                severity="info",
                                component="enums",
                                recommendation="Consider if extensions should belong to multiple categories",
                            )
                        )

        return errors

    @classmethod
    def _validate_cross_dependencies(cls) -> list[ConfigValidationError]:
        """
        Validate cross-field configuration constraints.

        Returns:
            List of detected configuration issues.
        """
        errors = []

        # Check Windows reserved names format
        for name in cls.WINDOWS_RESERVED_NAMES:
            if not name.islower():
                errors.append(
                    ConfigValidationError(
                        error_type="case_sensitive_reserved_name",
                        message=f"Windows reserved name '{name}' should be lowercase",
                        severity="warning",
                        component="reserved_names",
                        recommendation="Use lowercase for consistent case-insensitive matching",
                    )
                )

        # Validate Unicode character ranges
        for char_code in cls.DANGEROUS_UNICODE_CHARS:
            if not isinstance(char_code, int):
                errors.append(
                    ConfigValidationError(
                        error_type="invalid_unicode_char",
                        message=f"Unicode character code {char_code} is not an integer",
                        severity="error",
                        component="unicode",
                        recommendation="Use integer Unicode code points",
                    )
                )
            elif char_code < 0 or char_code > 0x10FFFF:
                errors.append(
                    ConfigValidationError(
                        error_type="invalid_unicode_range",
                        message=f"Unicode character code {char_code} is outside valid range",
                        severity="error",
                        component="unicode",
                        recommendation="Use valid Unicode code points (0-0x10FFFF)",
                    )
                )

        return errors

    @classmethod
    def validate_and_report(cls, strict: bool = True) -> None:
        """
        Validate configuration and log outcomes.

        Args:
            strict: If True, raise on errors/warnings.

        Raises:
            FileSecurityConfigurationError: If strict and issues found.
        """
        errors = cls.validate_configuration(strict=strict)

        if not errors:
            logger.info("File security configuration validation passed")
            return

        # Separate errors by severity
        error_list = [e for e in errors if e.severity == "error"]
        warning_list = [e for e in errors if e.severity == "warning"]
        info_list = [e for e in errors if e.severity == "info"]

        # Log validation results
        if error_list:
            for error in error_list:
                logger.error(
                    "Configuration error in %s: %s. %s",
                    error.component,
                    error.message,
                    error.recommendation,
                )

        if warning_list:
            for warning in warning_list:
                logger.warning(
                    "Configuration warning in %s: %s. %s",
                    warning.component,
                    warning.message,
                    warning.recommendation,
                )

        if info_list:
            for info in info_list:
                logger.info(
                    "Configuration info in %s: %s. %s",
                    info.component,
                    info.message,
                    info.recommendation,
                )

        # Raise exception if there are errors and strict mode is enabled
        if error_list and strict:
            raise FileSecurityConfigurationError(error_list)
        elif (error_list or warning_list) and strict:
            raise FileSecurityConfigurationError(error_list + warning_list)
