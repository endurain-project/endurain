"""File security exception classes and error codes."""

from dataclasses import dataclass


# ============================================================================
# Configuration Validation
# ============================================================================


@dataclass
class ConfigValidationError:
    """
    Configuration validation issue with severity and recommendation.

    Attributes:
        error_type: Type of the validation error.
        message: Human-readable error message.
        severity: Error severity level ('error', 'warning', 'info').
        component: Component that failed validation.
        recommendation: Optional recommendation to fix the issue.
    """

    error_type: str
    message: str
    severity: str  # 'error', 'warning', 'info'
    component: str
    recommendation: str = ""


class FileSecurityConfigurationError(Exception):
    """
    Configuration validation failed with aggregated errors.

    Args:
        errors: List of ConfigValidationError instances.

    Attributes:
        errors: List of validation errors that caused failure.
    """

    def __init__(self, errors: list[ConfigValidationError]):
        self.errors = errors
        error_messages = [
            f"{error.severity.upper()}: {error.message}" for error in errors
        ]
        super().__init__(
            f"Configuration validation failed: {'; '.join(error_messages)}"
        )


# ============================================================================
# Error Codes
# ============================================================================


class ErrorCode:
    """
    Machine-readable error codes for file validation failures.

    Attributes:
        Error codes are class-level string constants for various
        validation failure types.
    """

    # Filename validation errors
    FILENAME_EMPTY = "FILENAME_EMPTY"
    FILENAME_INVALID = "FILENAME_INVALID"
    FILENAME_TOO_LONG = "FILENAME_TOO_LONG"

    # Unicode security errors
    UNICODE_SECURITY = "UNICODE_SECURITY"
    UNICODE_DANGEROUS_CHARS = "UNICODE_DANGEROUS_CHARS"
    UNICODE_NORMALIZATION_ERROR = "UNICODE_NORMALIZATION_ERROR"

    # Extension validation errors
    EXTENSION_BLOCKED = "EXTENSION_BLOCKED"
    EXTENSION_NOT_ALLOWED = "EXTENSION_NOT_ALLOWED"
    COMPOUND_EXTENSION_BLOCKED = "COMPOUND_EXTENSION_BLOCKED"
    EXTENSION_MISSING = "EXTENSION_MISSING"

    # Windows security errors
    WINDOWS_RESERVED_NAME = "WINDOWS_RESERVED_NAME"

    # File size errors
    FILE_TOO_LARGE = "FILE_TOO_LARGE"
    FILE_EMPTY = "FILE_EMPTY"
    FILE_SIZE_UNKNOWN = "FILE_SIZE_UNKNOWN"

    # MIME type errors
    MIME_TYPE_INVALID = "MIME_TYPE_INVALID"
    MIME_TYPE_MISMATCH = "MIME_TYPE_MISMATCH"
    MIME_DETECTION_FAILED = "MIME_DETECTION_FAILED"

    # File signature errors
    FILE_SIGNATURE_INVALID = "FILE_SIGNATURE_INVALID"
    FILE_SIGNATURE_MISSING = "FILE_SIGNATURE_MISSING"
    FILE_SIGNATURE_MISMATCH = "FILE_SIGNATURE_MISMATCH"

    # Compression and ZIP errors
    ZIP_BOMB_DETECTED = "ZIP_BOMB_DETECTED"
    ZIP_CONTENT_THREAT = "ZIP_CONTENT_THREAT"
    COMPRESSION_RATIO_EXCEEDED = "COMPRESSION_RATIO_EXCEEDED"
    ZIP_TOO_MANY_ENTRIES = "ZIP_TOO_MANY_ENTRIES"
    ZIP_INVALID_STRUCTURE = "ZIP_INVALID_STRUCTURE"
    ZIP_CORRUPT = "ZIP_CORRUPT"
    ZIP_TOO_LARGE = "ZIP_TOO_LARGE"
    ZIP_NESTED_ARCHIVE = "ZIP_NESTED_ARCHIVE"
    ZIP_DIRECTORY_TRAVERSAL = "ZIP_DIRECTORY_TRAVERSAL"
    ZIP_SYMLINK_DETECTED = "ZIP_SYMLINK_DETECTED"
    ZIP_ABSOLUTE_PATH = "ZIP_ABSOLUTE_PATH"
    ZIP_ANALYSIS_TIMEOUT = "ZIP_ANALYSIS_TIMEOUT"

    # Processing errors
    PROCESSING_ERROR = "PROCESSING_ERROR"
    IO_ERROR = "IO_ERROR"
    MEMORY_ERROR = "MEMORY_ERROR"


# ============================================================================
# Base Exceptions
# ============================================================================


class FileSecurityError(Exception):
    """
    Base exception for all file security validation failures.

    Args:
        message: Human-readable error description.
        error_code: Optional machine-readable error code.

    Attributes:
        message: Human-readable error message.
        error_code: Machine-readable error code from ErrorCode.
    """

    def __init__(self, message: str, error_code: str | None = None):
        self.message = message
        self.error_code = error_code
        super().__init__(message)


# ============================================================================
# File Validation Exceptions
# ============================================================================


class FileValidationError(FileSecurityError):
    """
    File validation failed.

    Args:
        message: Human-readable error description.
        filename: Optional name of the file that failed validation.
        error_code: Optional machine-readable error code.

    Attributes:
        filename: Name of the file that failed validation.
    """

    def __init__(
        self,
        message: str,
        filename: str | None = None,
        error_code: str | None = None,
    ):
        self.filename = filename
        super().__init__(message, error_code)


# ============================================================================
# Filename Security Exceptions
# ============================================================================


class FilenameSecurityError(FileValidationError):
    """Filename failed security checks."""

    pass


class UnicodeSecurityError(FilenameSecurityError):
    """
    Dangerous Unicode characters detected in filename.

    Args:
        message: Human-readable error description.
        filename: Optional filename containing dangerous Unicode.
        dangerous_chars: Optional list of (char, code_point, position)
            tuples for each dangerous character found.

    Attributes:
        dangerous_chars: List of dangerous character tuples.
    """

    def __init__(
        self,
        message: str,
        filename: str | None = None,
        dangerous_chars: list[tuple[str, int, int]] | None = None,
    ):
        self.dangerous_chars = dangerous_chars or []
        super().__init__(
            message,
            filename=filename,
            error_code=ErrorCode.UNICODE_DANGEROUS_CHARS,
        )


class ExtensionSecurityError(FilenameSecurityError):
    """
    Dangerous file extension detected.

    Args:
        message: Human-readable error description.
        filename: Optional filename with dangerous extension.
        extension: Optional specific extension that was blocked.
        error_code: Optional error code (defaults to
            EXTENSION_BLOCKED).

    Attributes:
        extension: The specific extension that was blocked.
    """

    def __init__(
        self,
        message: str,
        filename: str | None = None,
        extension: str | None = None,
        error_code: str | None = None,
    ):
        self.extension = extension
        super().__init__(
            message,
            filename=filename,
            error_code=error_code or ErrorCode.EXTENSION_BLOCKED,
        )


class WindowsReservedNameError(FilenameSecurityError):
    """
    Windows reserved device name used.

    Args:
        message: Human-readable error description.
        filename: Optional filename using a reserved name.
        reserved_name: Optional specific reserved name detected.

    Attributes:
        reserved_name: The specific reserved name that was detected.
    """

    def __init__(
        self,
        message: str,
        filename: str | None = None,
        reserved_name: str | None = None,
    ):
        self.reserved_name = reserved_name
        super().__init__(
            message,
            filename=filename,
            error_code=ErrorCode.WINDOWS_RESERVED_NAME,
        )


# ============================================================================
# File Content Exceptions
# ============================================================================


class FileSizeError(FileValidationError):
    """
    File exceeds configured size limits.

    Args:
        message: Human-readable error description.
        filename: Optional filename that exceeded size limits.
        size: Optional actual file size in bytes.
        max_size: Optional maximum allowed size in bytes.

    Attributes:
        size: The actual file size in bytes.
        max_size: The maximum allowed size in bytes.
    """

    def __init__(
        self,
        message: str,
        filename: str | None = None,
        size: int | None = None,
        max_size: int | None = None,
    ):
        self.size = size
        self.max_size = max_size
        super().__init__(
            message, filename=filename, error_code=ErrorCode.FILE_TOO_LARGE
        )


class MimeTypeError(FileValidationError):
    """
    File MIME type not allowed or mismatches extension.

    Args:
        message: Human-readable error description.
        filename: Optional filename with MIME type issue.
        detected_mime: Optional detected MIME type string.
        allowed_mimes: Optional list of allowed MIME types.
        error_code: Optional error code (defaults to
            MIME_TYPE_INVALID).

    Attributes:
        detected_mime: The detected MIME type string.
        allowed_mimes: List of allowed MIME types.
    """

    def __init__(
        self,
        message: str,
        filename: str | None = None,
        detected_mime: str | None = None,
        allowed_mimes: list[str] | None = None,
        error_code: str | None = None,
    ):
        self.detected_mime = detected_mime
        self.allowed_mimes = allowed_mimes or []
        super().__init__(
            message,
            filename=filename,
            error_code=error_code or ErrorCode.MIME_TYPE_INVALID,
        )


class FileSignatureError(FileValidationError):
    """
    File header signature invalid or mismatched.

    Args:
        message: Human-readable error description.
        filename: Optional filename with signature issue.
        expected_type: Optional expected file type based on extension.

    Attributes:
        expected_type: The expected file type based on extension.
    """

    def __init__(
        self,
        message: str,
        filename: str | None = None,
        expected_type: str | None = None,
    ):
        self.expected_type = expected_type
        super().__init__(
            message,
            filename=filename,
            error_code=ErrorCode.FILE_SIGNATURE_MISMATCH,
        )


# ============================================================================
# Compression and ZIP Exceptions
# ============================================================================


class CompressionSecurityError(FileValidationError):
    """
    Compressed file security check failed.

    Args:
        message: Human-readable error description.
        filename: Optional filename of compressed file.
        error_code: Optional error code (defaults to
            COMPRESSION_GENERIC).

    Attributes:
        None beyond inherited FileValidationError attributes.
    """

    pass


class ZipBombError(CompressionSecurityError):
    """
    Zip archive exceeds compression ratio or uncompressed size limits.

    Args:
        message: Human-readable error description.
        filename: Optional filename of zip bomb.
        compression_ratio: Optional actual compression ratio detected.
        uncompressed_size: Optional total uncompressed size in bytes.
        max_ratio: Optional maximum allowed compression ratio.
        max_size: Optional maximum allowed uncompressed size in bytes.

    Attributes:
        compression_ratio: Actual compression ratio detected.
        uncompressed_size: Total uncompressed size in bytes.
        max_ratio: Maximum allowed compression ratio.
        max_size: Maximum allowed uncompressed size in bytes.
    """

    def __init__(
        self,
        message: str,
        filename: str | None = None,
        compression_ratio: float | None = None,
        uncompressed_size: int | None = None,
        max_ratio: float | None = None,
        max_size: int | None = None,
    ):
        self.compression_ratio = compression_ratio
        self.uncompressed_size = uncompressed_size
        self.max_ratio = max_ratio
        self.max_size = max_size
        super().__init__(
            message,
            filename=filename,
            error_code=ErrorCode.ZIP_BOMB_DETECTED,
        )


class ZipContentError(CompressionSecurityError):
    """
    Zip archive contains dangerous content or structure.

    Args:
        message: Human-readable error description.
        filename: Optional filename of problematic archive.
        threats: Optional list of detected threat descriptions.
        error_code: Optional error code (defaults to
            ZIP_CONTENT_THREAT).

    Attributes:
        threats: List of detected threat descriptions.
    """

    def __init__(
        self,
        message: str,
        filename: str | None = None,
        threats: list[str] | None = None,
        error_code: str | None = None,
    ):
        self.threats = threats or []
        super().__init__(
            message,
            filename=filename,
            error_code=error_code or ErrorCode.ZIP_CONTENT_THREAT,
        )


class FileProcessingError(FileSecurityError):
    """
    Unexpected processing error during file validation.

    Args:
        message: Human-readable error description.
        original_error: Optional original exception that was caught.

    Attributes:
        original_error: The original exception that was caught.
    """

    def __init__(self, message: str, original_error: Exception | None = None):
        self.original_error = original_error
        super().__init__(message, error_code=ErrorCode.PROCESSING_ERROR)
