import os
import time
import mimetypes
import unicodedata
import zipfile
import io
import magic
from enum import Enum
from typing import Set, Tuple, List
from dataclasses import dataclass
from fastapi import HTTPException, status, UploadFile

import core.logger as core_logger


@dataclass
class SecurityLimits:
    
    # File size limits (in bytes)
    max_image_size: int = 20 * 1024 * 1024  # 20MB for images
    max_zip_size: int = 500 * 1024 * 1024   # 500MB for ZIP files
    
    # ZIP compression security settings
    max_compression_ratio: int = 100  # Maximum allowed expansion ratio (e.g., 100:1)
    max_uncompressed_size: int = 1024 * 1024 * 1024  # 1GB max uncompressed size
    max_zip_entries: int = 10000  # Maximum number of files in ZIP archive
    zip_analysis_timeout: float = 5.0  # Maximum seconds to spend analyzing ZIP structure
    
    # ZIP content inspection settings
    max_zip_depth: int = 10  # Maximum nesting depth for directories in ZIP
    max_filename_length: int = 255  # Maximum length for individual file names
    max_path_length: int = 1024  # Maximum length for full file paths
    allow_nested_archives: bool = False  # Whether to allow nested archive files
    allow_symlinks: bool = False  # Whether to allow symbolic links in ZIP
    allow_absolute_paths: bool = False  # Whether to allow absolute paths in ZIP
    scan_zip_content: bool = True  # Whether to perform deep content inspection


@dataclass
class ConfigValidationError:
    error_type: str
    message: str
    severity: str  # 'error', 'warning', 'info'
    component: str
    recommendation: str = ""


class FileSecurityConfigurationError(Exception):
    
    def __init__(self, errors: List[ConfigValidationError]):
        self.errors = errors
        error_messages = [f"{error.severity.upper()}: {error.message}" for error in errors]
        super().__init__(f"Configuration validation failed: {'; '.join(error_messages)}")


class DangerousExtensionCategory(Enum):
    
    # Traditional Windows executables
    WINDOWS_EXECUTABLES = {
        ".exe", ".bat", ".cmd", ".com", ".pif", ".scr", ".msi", ".dll"
    }
    
    # Script files that can execute code
    SCRIPT_FILES = {
        ".vbs", ".js", ".jse", ".wsf", ".wsh", ".hta", ".ps1", ".psm1", 
        ".ps1xml", ".psc1", ".psd1", ".pssc", ".cdxml", ".xaml"
    }
    
    # Web server and dynamic content scripts
    WEB_SCRIPTS = {
        ".jsp", ".php", ".php3", ".php4", ".php5", ".phtml", ".asp", 
        ".aspx", ".cer", ".cgi", ".pl", ".py", ".rb", ".go", ".lua"
    }
    
    # Unix/Linux executables and shell scripts
    UNIX_EXECUTABLES = {
        ".sh", ".bash", ".zsh", ".fish", ".csh", ".ksh", ".tcsh", 
        ".run", ".bin", ".out", ".elf", ".so", ".a"
    }
    
    # macOS specific executables and applications
    MACOS_EXECUTABLES = {
        ".app", ".dmg", ".pkg", ".mpkg", ".command", ".tool", 
        ".workflow", ".action", ".dylib", ".bundle", ".framework"
    }
    
    # Java related executables and bytecode
    JAVA_EXECUTABLES = {
        ".jar", ".war", ".ear", ".jnlp", ".class"
    }
    
    # Mobile application packages
    MOBILE_APPS = {
        ".apk", ".aab", ".ipa", ".appx", ".msix", ".xap"
    }
    
    # Browser extensions and web applications
    BROWSER_EXTENSIONS = {
        ".crx", ".xpi", ".safariextz", ".oex", ".nex", ".user.js", ".gadget"
    }
    
    # Modern package managers and distribution formats
    PACKAGE_FORMATS = {
        ".deb", ".rpm", ".snap", ".flatpak", ".appimage", ".vsix", 
        ".nupkg", ".gem", ".whl", ".egg"
    }
    
    # Archive formats that can contain executables
    ARCHIVE_FORMATS = {
        ".7z", ".rar", ".cab", ".ace", ".arj", ".lzh", ".lha", ".zoo"
    }
    
    # Virtualization and container formats
    VIRTUALIZATION_FORMATS = {
        ".ova", ".ovf", ".vmdk", ".vdi", ".vhd", ".vhdx", ".qcow2", ".docker"
    }
    
    # Office documents with macro capabilities
    OFFICE_MACROS = {
        ".docm", ".dotm", ".xlsm", ".xltm", ".xlam", ".pptm", 
        ".potm", ".ppam", ".sldm"
    }
    
    # System shortcuts and configuration files
    SYSTEM_FILES = {
        ".url", ".website", ".webloc", ".desktop", ".lnk", ".application", 
        ".manifest", ".deploy", ".msu", ".patch", ".diff", ".reg", ".inf"
    }
    
    # System drivers and low-level components
    SYSTEM_DRIVERS = {
        ".sys", ".drv", ".ocx", ".cpl"
    }
    
    # Windows theme and customization files
    WINDOWS_THEMES = {
        ".theme", ".themepack", ".scf", ".shs", ".shb", ".sct", 
        ".ws", ".job", ".msc"
    }
    
    # Help and documentation files that can execute code
    HELP_FILES = {
        ".chm", ".hlp"
    }


class CompoundExtensionCategory(Enum):
    
    # Compressed archive formats
    COMPRESSED_ARCHIVES = {
        ".tar.xz", ".tar.gz", ".tar.bz2", ".tar.lz", ".tar.lzma", 
        ".tar.Z", ".tgz", ".tbz2"
    }
    
    # JavaScript related compound extensions
    JAVASCRIPT_VARIANTS = {
        ".user.js", ".backup.js", ".min.js", ".worker.js"
    }
    
    # Web content compound extensions
    WEB_CONTENT = {
        ".min.css", ".min.html"
    }


class UnicodeAttackCategory(Enum):
    
    # Right-to-Left and directional override characters
    DIRECTIONAL_OVERRIDES = {
        0x202E,  # U+202E RIGHT-TO-LEFT OVERRIDE
        0x202D,  # U+202D LEFT-TO-RIGHT OVERRIDE
        0x202A,  # U+202A LEFT-TO-RIGHT EMBEDDING
        0x202B,  # U+202B RIGHT-TO-LEFT EMBEDDING
        0x202C,  # U+202C POP DIRECTIONAL FORMATTING
        0x2066,  # U+2066 LEFT-TO-RIGHT ISOLATE
        0x2067,  # U+2067 RIGHT-TO-LEFT ISOLATE
        0x2068,  # U+2068 FIRST STRONG ISOLATE
        0x2069,  # U+2069 POP DIRECTIONAL ISOLATE
    }
    
    # Zero-width and invisible characters
    ZERO_WIDTH_CHARACTERS = {
        0x200B,  # U+200B ZERO WIDTH SPACE
        0x200C,  # U+200C ZERO WIDTH NON-JOINER
        0x200D,  # U+200D ZERO WIDTH JOINER
        0x2060,  # U+2060 WORD JOINER
        0xFEFF,  # U+FEFF ZERO WIDTH NO-BREAK SPACE (BOM)
        0x034F,  # U+034F COMBINING GRAPHEME JOINER
    }
    
    # Language and format specific characters
    LANGUAGE_MARKS = {
        0x061C,  # U+061C ARABIC LETTER MARK
        0x180E,  # U+180E MONGOLIAN VOWEL SEPARATOR
    }
    
    # Confusing punctuation that can disguise extensions
    CONFUSING_PUNCTUATION = {
        0x2024,  # U+2024 ONE DOT LEADER
        0x2025,  # U+2025 TWO DOT LEADER
        0x2026,  # U+2026 HORIZONTAL ELLIPSIS
        0xFF0E,  # U+FF0E FULLWIDTH FULL STOP
    }


class SuspiciousFilePattern(Enum):
    
    # Directory traversal attack patterns
    DIRECTORY_TRAVERSAL = {
        "../", "..\\", ".../", "...\\",
        "....//", "....\\\\", 
        "%2e%2e%2f", "%2e%2e%5c",  # URL encoded ../ and ..\
        "%252e%252e%252f", "%252e%252e%255c"  # Double URL encoded
    }
    
    # Suspicious filename patterns
    SUSPICIOUS_NAMES = {
        # Windows system files that shouldn't be in user uploads
        "autorun.inf", "desktop.ini", "thumbs.db", ".ds_store",
        # Common malware names
        "install.exe", "setup.exe", "update.exe", "patch.exe",
        "crack.exe", "keygen.exe", "loader.exe", "activator.exe",
        # Hidden or system-like files
        ".htaccess", ".htpasswd", "web.config", "robots.txt"
    }
    
    # Dangerous file content signatures (magic bytes)
    EXECUTABLE_SIGNATURES = {
        # Windows PE executables
        b"MZ", b"PE\x00\x00",
        # ELF executables (Linux)
        b"\x7fELF",
        # Mach-O executables (macOS)
        b"\xfe\xed\xfa\xce", b"\xfe\xed\xfa\xcf",
        b"\xce\xfa\xed\xfe", b"\xcf\xfa\xed\xfe",
        # Java class files
        b"\xca\xfe\xba\xbe",
        # Windows shortcuts (.lnk)
        b"L\x00\x00\x00"
    }
    
    # Suspicious path components
    SUSPICIOUS_PATHS = {
        # Windows system directories
        "windows/", "system32/", "syswow64/", "programfiles/",
        # Unix system directories
        "/bin/", "/sbin/", "/usr/bin/", "/usr/sbin/", "/etc/",
        # Web server directories
        "cgi-bin/", "htdocs/", "www/", "wwwroot/",
        # Development/build directories
        ".git/", ".svn/", "node_modules/", "__pycache__/"
    }


class ZipThreatCategory(Enum):
    
    # Archive format threats
    NESTED_ARCHIVES = {
        ".zip", ".rar", ".7z", ".tar", ".gz", ".bz2", ".xz", 
        ".tar.gz", ".tar.bz2", ".tar.xz", ".tgz", ".tbz2"
    }
    
    # Executable content threats
    EXECUTABLE_FILES = {
        ".exe", ".com", ".bat", ".cmd", ".scr", ".pif",
        ".bin", ".run", ".app", ".deb", ".rpm", ".msi"
    }
    
    # Script and code threats
    SCRIPT_FILES = {
        ".js", ".vbs", ".ps1", ".sh", ".bash", ".py", ".php", 
        ".pl", ".rb", ".lua", ".asp", ".jsp"
    }
    
    # System and configuration threats
    SYSTEM_FILES = {
        ".dll", ".so", ".dylib", ".sys", ".drv", ".inf", 
        ".reg", ".cfg", ".conf", ".ini"
    }


class FileSecurityConfig:
    # Security limits configuration
    limits = SecurityLimits()

    # Allowed MIME types for images
    ALLOWED_IMAGE_MIMES: Set[str] = {"image/jpeg", "image/jpg", "image/png"}

    # Allowed MIME types for ZIP files
    ALLOWED_ZIP_MIMES: Set[str] = {
        "application/zip",
        "application/x-zip-compressed",
        "multipart/x-zip",
    }

    # Allowed file extensions
    ALLOWED_IMAGE_EXTENSIONS: Set[str] = {".jpg", ".jpeg", ".png"}
    ALLOWED_ZIP_EXTENSIONS: Set[str] = {".zip"}

    # Generate dangerous file extensions from categorized enums
    @staticmethod
    def _generate_blocked_extensions() -> Set[str]:
        blocked_extensions = set()
        
        # Combine all dangerous extension categories
        for category in DangerousExtensionCategory:
            blocked_extensions.update(category.value)
        
        return blocked_extensions

    # Generate compound dangerous file extensions from categorized enums
    @staticmethod
    def _generate_compound_blocked_extensions() -> Set[str]:
        compound_extensions = set()
        
        # Combine all compound extension categories
        for category in CompoundExtensionCategory:
            compound_extensions.update(category.value)
        
        return compound_extensions

    # Generate dangerous Unicode characters from categorized enums
    @staticmethod
    def _generate_dangerous_unicode_chars() -> Set[int]:
        dangerous_chars = set()
        
        # Combine all Unicode attack categories
        for category in UnicodeAttackCategory:
            dangerous_chars.update(category.value)
        
        return dangerous_chars

    # Dangerous file extensions to explicitly block (generated from enums)
    BLOCKED_EXTENSIONS: Set[str] = _generate_blocked_extensions()

    # Compound dangerous file extensions (multi-part extensions)
    # These are checked as complete strings, not individual parts
    COMPOUND_BLOCKED_EXTENSIONS: Set[str] = _generate_compound_blocked_extensions()

    # Dangerous Unicode characters that can be used for filename attacks
    # These characters can disguise file extensions or cause rendering issues
    DANGEROUS_UNICODE_CHARS: Set[int] = _generate_dangerous_unicode_chars()

    # Windows reserved names that cannot be used as filenames
    # These names are reserved by Windows regardless of extension
    WINDOWS_RESERVED_NAMES: Set[str] = {
        "con", "prn", "aux", "nul",
        "com1", "com2", "com3", "com4", "com5", "com6", "com7", "com8", "com9",
        "lpt1", "lpt2", "lpt3", "lpt4", "lpt5", "lpt6", "lpt7", "lpt8", "lpt9",
    }

    # Configuration validation trigger
    @classmethod
    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        # Perform validation with warnings allowed (non-strict mode)
        try:
            cls.validate_and_report(strict=False)
        except Exception as err:
            core_logger.print_to_log(f"Warning: Configuration validation failed: {err}", "warning")

    @classmethod
    def get_extensions_by_category(cls, category: DangerousExtensionCategory) -> Set[str]:
        return category.value.copy()
    
    @classmethod
    def get_compound_extensions_by_category(cls, category: CompoundExtensionCategory) -> Set[str]:
        return category.value.copy()
    
    @classmethod
    def get_unicode_chars_by_category(cls, category: UnicodeAttackCategory) -> Set[int]:
        return category.value.copy()
    
    @classmethod
    def is_extension_in_category(cls, extension: str, category: DangerousExtensionCategory) -> bool:
        return extension.lower() in category.value
    
    @classmethod
    def get_extension_category(cls, extension: str) -> DangerousExtensionCategory | None:
        extension_lower = extension.lower()
        for category in DangerousExtensionCategory:
            if extension_lower in category.value:
                return category
        return None
    
    @classmethod
    def validate_configuration(cls, strict: bool = True) -> List[ConfigValidationError]:
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
    def _validate_file_size_limits(cls) -> List[ConfigValidationError]:
        errors = []
        
        # Check image size limits
        if cls.limits.max_image_size <= 0:
            errors.append(ConfigValidationError(
                error_type="invalid_size_limit",
                message="max_image_size must be greater than 0",
                severity="error",
                component="file_sizes",
                recommendation="Set max_image_size to a positive value (e.g., 20MB)"
            ))
        
        if cls.limits.max_image_size > 100 * 1024 * 1024:  # 100MB
            errors.append(ConfigValidationError(
                error_type="excessive_size_limit",
                message=f"max_image_size ({cls.limits.max_image_size // (1024*1024)}MB) is very large",
                severity="warning",
                component="file_sizes",
                recommendation="Consider reducing image size limit to prevent resource exhaustion"
            ))
        
        # Check ZIP size limits
        if cls.limits.max_zip_size <= 0:
            errors.append(ConfigValidationError(
                error_type="invalid_size_limit",
                message="max_zip_size must be greater than 0",
                severity="error",
                component="file_sizes",
                recommendation="Set max_zip_size to a positive value (e.g., 500MB)"
            ))
        
        if cls.limits.max_zip_size > 2 * 1024 * 1024 * 1024:  # 2GB
            errors.append(ConfigValidationError(
                error_type="excessive_size_limit",
                message=f"max_zip_size ({cls.limits.max_zip_size // (1024*1024)}MB) is very large",
                severity="warning",
                component="file_sizes",
                recommendation="Consider reducing ZIP size limit to prevent resource exhaustion"
            ))
        
        # Validate size relationship
        if cls.limits.max_zip_size <= cls.limits.max_image_size:
            errors.append(ConfigValidationError(
                error_type="inconsistent_size_limits",
                message="max_zip_size should typically be larger than max_image_size",
                severity="warning",
                component="file_sizes",
                recommendation="ZIP files usually contain multiple files and should have higher limits"
            ))
        
        return errors
    
    @classmethod
    def _validate_mime_configurations(cls) -> List[ConfigValidationError]:
        errors = []
        
        # Check image MIME types
        if not cls.ALLOWED_IMAGE_MIMES:
            errors.append(ConfigValidationError(
                error_type="empty_mime_set",
                message="ALLOWED_IMAGE_MIMES cannot be empty",
                severity="error",
                component="mime_types",
                recommendation="Add at least one allowed image MIME type"
            ))
        
        # Validate image MIME type format
        for mime_type in cls.ALLOWED_IMAGE_MIMES:
            if not mime_type.startswith("image/"):
                errors.append(ConfigValidationError(
                    error_type="invalid_image_mime",
                    message=f"Image MIME type '{mime_type}' should start with 'image/'",
                    severity="warning",
                    component="mime_types",
                    recommendation="Use standard image MIME types like 'image/jpeg', 'image/png'"
                ))
        
        # Check ZIP MIME types
        if not cls.ALLOWED_ZIP_MIMES:
            errors.append(ConfigValidationError(
                error_type="empty_mime_set",
                message="ALLOWED_ZIP_MIMES cannot be empty",
                severity="error",
                component="mime_types",
                recommendation="Add at least one allowed ZIP MIME type"
            ))
        
        # Check for duplicate MIME types
        all_mimes = list(cls.ALLOWED_IMAGE_MIMES) + list(cls.ALLOWED_ZIP_MIMES)
        duplicates = set([mime for mime in all_mimes if all_mimes.count(mime) > 1])
        if duplicates:
            errors.append(ConfigValidationError(
                error_type="duplicate_mime_types",
                message=f"Duplicate MIME types found: {duplicates}",
                severity="warning",
                component="mime_types",
                recommendation="Remove duplicate MIME types to avoid confusion"
            ))
        
        return errors
    
    @classmethod
    def _validate_extension_configurations(cls) -> List[ConfigValidationError]:
        errors = []
        
        # Check extension format
        for ext_set_name, ext_set in [
            ("ALLOWED_IMAGE_EXTENSIONS", cls.ALLOWED_IMAGE_EXTENSIONS),
            ("ALLOWED_ZIP_EXTENSIONS", cls.ALLOWED_ZIP_EXTENSIONS),
        ]:
            if not ext_set:
                errors.append(ConfigValidationError(
                    error_type="empty_extension_set",
                    message=f"{ext_set_name} cannot be empty",
                    severity="error",
                    component="extensions",
                    recommendation=f"Add at least one extension to {ext_set_name}"
                ))
            
            for ext in ext_set:
                if not ext.startswith("."):
                    errors.append(ConfigValidationError(
                        error_type="invalid_extension_format",
                        message=f"Extension '{ext}' in {ext_set_name} should start with '.'",
                        severity="error",
                        component="extensions",
                        recommendation="Use format '.ext' for file extensions"
                    ))
        
        # Check blocked extensions
        if not cls.BLOCKED_EXTENSIONS:
            errors.append(ConfigValidationError(
                error_type="empty_blocked_extensions",
                message="BLOCKED_EXTENSIONS is empty - security risk",
                severity="error",
                component="extensions",
                recommendation="Ensure dangerous extensions are properly blocked"
            ))
        
        # Check for overlap between allowed and blocked extensions
        image_blocked = cls.ALLOWED_IMAGE_EXTENSIONS.intersection(cls.BLOCKED_EXTENSIONS)
        if image_blocked:
            errors.append(ConfigValidationError(
                error_type="extension_conflict",
                message=f"Image extensions {image_blocked} are both allowed and blocked",
                severity="error",
                component="extensions",
                recommendation="Remove conflicts between allowed and blocked extensions"
            ))
        
        zip_blocked = cls.ALLOWED_ZIP_EXTENSIONS.intersection(cls.BLOCKED_EXTENSIONS)
        if zip_blocked:
            errors.append(ConfigValidationError(
                error_type="extension_conflict",
                message=f"ZIP extensions {zip_blocked} are both allowed and blocked",
                severity="error",
                component="extensions",
                recommendation="Remove conflicts between allowed and blocked extensions"
            ))
        
        # Check compound extension consistency
        compound_overlap = cls.BLOCKED_EXTENSIONS.intersection(cls.COMPOUND_BLOCKED_EXTENSIONS)
        if compound_overlap:
            errors.append(ConfigValidationError(
                error_type="compound_extension_overlap",
                message=f"Extensions {compound_overlap} appear in both blocked and compound blocked lists",
                severity="warning",
                component="extensions",
                recommendation="Compound extensions should only be in COMPOUND_BLOCKED_EXTENSIONS"
            ))
        
        return errors
    
    @classmethod
    def _validate_compression_settings(cls) -> List[ConfigValidationError]:
        """Validate ZIP compression and analysis settings."""
        errors = []
        
        # Validate compression ratio
        if cls.limits.max_compression_ratio <= 0:
            errors.append(ConfigValidationError(
                error_type="invalid_compression_ratio",
                message="max_compression_ratio must be greater than 0",
                severity="error",
                component="compression",
                recommendation="Set a reasonable compression ratio limit (e.g., 100:1)"
            ))
        
        if cls.limits.max_compression_ratio < 10:
            errors.append(ConfigValidationError(
                error_type="too_strict_compression",
                message=f"max_compression_ratio ({cls.limits.max_compression_ratio}) is very strict",
                severity="warning",
                component="compression",
                recommendation="Consider allowing higher compression ratios for legitimate files"
            ))
        
        if cls.limits.max_compression_ratio > 1000:
            errors.append(ConfigValidationError(
                error_type="too_permissive_compression",
                message=f"max_compression_ratio ({cls.limits.max_compression_ratio}) may allow zip bombs",
                severity="warning",
                component="compression",
                recommendation="Reduce compression ratio limit to prevent zip bomb attacks"
            ))
        
        # Validate uncompressed size limit
        if cls.limits.max_uncompressed_size <= 0:
            errors.append(ConfigValidationError(
                error_type="invalid_uncompressed_size",
                message="max_uncompressed_size must be greater than 0",
                severity="error",
                component="compression",
                recommendation="Set a reasonable uncompressed size limit"
            ))
        
        # Validate ZIP entry limits
        if cls.limits.max_zip_entries <= 0:
            errors.append(ConfigValidationError(
                error_type="invalid_zip_entries",
                message="max_zip_entries must be greater than 0",
                severity="error",
                component="compression",
                recommendation="Set a reasonable limit for ZIP file entries"
            ))
        
        if cls.limits.max_zip_entries > 100000:
            errors.append(ConfigValidationError(
                error_type="excessive_zip_entries",
                message=f"max_zip_entries ({cls.limits.max_zip_entries}) is very high",
                severity="warning",
                component="compression",
                recommendation="High entry limits may impact performance"
            ))
        
        # Validate timeout settings
        if cls.limits.zip_analysis_timeout <= 0:
            errors.append(ConfigValidationError(
                error_type="invalid_timeout",
                message="zip_analysis_timeout must be greater than 0",
                severity="error",
                component="compression",
                recommendation="Set a reasonable timeout for ZIP analysis"
            ))
        
        if cls.limits.zip_analysis_timeout > 30:
            errors.append(ConfigValidationError(
                error_type="excessive_timeout",
                message=f"zip_analysis_timeout ({cls.limits.zip_analysis_timeout}s) is very long",
                severity="warning",
                component="compression",
                recommendation="Long timeouts may impact user experience"
            ))
        
        return errors
    
    @classmethod
    def _validate_enum_consistency(cls) -> List[ConfigValidationError]:
        errors = []
        
        # Check for empty enum categories
        for category in DangerousExtensionCategory:
            if not category.value:
                errors.append(ConfigValidationError(
                    error_type="empty_enum_category",
                    message=f"Extension category {category.name} is empty",
                    severity="warning",
                    component="enums",
                    recommendation=f"Add extensions to {category.name} or remove unused category"
                ))
        
        for category in CompoundExtensionCategory:
            if not category.value:
                errors.append(ConfigValidationError(
                    error_type="empty_enum_category",
                    message=f"Compound extension category {category.name} is empty",
                    severity="warning",
                    component="enums",
                    recommendation=f"Add extensions to {category.name} or remove unused category"
                ))
        
        for category in UnicodeAttackCategory:
            if not category.value:
                errors.append(ConfigValidationError(
                    error_type="empty_enum_category",
                    message=f"Unicode attack category {category.name} is empty",
                    severity="warning",
                    component="enums",
                    recommendation=f"Add Unicode characters to {category.name} or remove unused category"
                ))
        
        # Check for overlapping extensions between categories
        all_extensions_by_category = {}
        for category in DangerousExtensionCategory:
            all_extensions_by_category[category.name] = category.value
        
        for cat1_name, cat1_exts in all_extensions_by_category.items():
            for cat2_name, cat2_exts in all_extensions_by_category.items():
                if cat1_name != cat2_name:
                    overlap = cat1_exts.intersection(cat2_exts)
                    if overlap:
                        errors.append(ConfigValidationError(
                            error_type="category_overlap",
                            message=f"Categories {cat1_name} and {cat2_name} share extensions: {overlap}",
                            severity="info",
                            component="enums",
                            recommendation="Consider if extensions should belong to multiple categories"
                        ))
        
        return errors
    
    @classmethod
    def _validate_cross_dependencies(cls) -> List[ConfigValidationError]:
        errors = []
        
        # Check Windows reserved names format
        for name in cls.WINDOWS_RESERVED_NAMES:
            if not name.islower():
                errors.append(ConfigValidationError(
                    error_type="case_sensitive_reserved_name",
                    message=f"Windows reserved name '{name}' should be lowercase",
                    severity="warning",
                    component="reserved_names",
                    recommendation="Use lowercase for consistent case-insensitive matching"
                ))
        
        # Validate Unicode character ranges
        for char_code in cls.DANGEROUS_UNICODE_CHARS:
            if not isinstance(char_code, int):
                errors.append(ConfigValidationError(
                    error_type="invalid_unicode_char",
                    message=f"Unicode character code {char_code} is not an integer",
                    severity="error",
                    component="unicode",
                    recommendation="Use integer Unicode code points"
                ))
            elif char_code < 0 or char_code > 0x10FFFF:
                errors.append(ConfigValidationError(
                    error_type="invalid_unicode_range",
                    message=f"Unicode character code {char_code} is outside valid range",
                    severity="error",
                    component="unicode",
                    recommendation="Use valid Unicode code points (0-0x10FFFF)"
                ))
        
        return errors
    
    @classmethod
    def validate_and_report(cls, strict: bool = True) -> None:
        errors = cls.validate_configuration(strict=strict)
        
        if not errors:
            core_logger.print_to_log("File security configuration validation passed", "info")
            return
        
        # Separate errors by severity
        error_list = [e for e in errors if e.severity == "error"]
        warning_list = [e for e in errors if e.severity == "warning"]
        info_list = [e for e in errors if e.severity == "info"]
        
        # Log validation results
        if error_list:
            for error in error_list:
                core_logger.print_to_log(
                    f"Configuration ERROR in {error.component}: {error.message}. {error.recommendation}",
                    "error"
                )
        
        if warning_list:
            for warning in warning_list:
                core_logger.print_to_log(
                    f"Configuration WARNING in {warning.component}: {warning.message}. {warning.recommendation}",
                    "warning"
                )
        
        if info_list:
            for info in info_list:
                core_logger.print_to_log(
                    f"Configuration INFO in {info.component}: {info.message}. {info.recommendation}",
                    "info"
                )
        
        # Raise exception if there are errors and strict mode is enabled
        if error_list and strict:
            raise FileSecurityConfigurationError(error_list)
        elif (error_list or warning_list) and strict:
            raise FileSecurityConfigurationError(error_list + warning_list)


class UnicodeSecurityValidator:

    def __init__(self, config: FileSecurityConfig):
        self.config = config

    def validate_unicode_security(self, filename: str) -> str:
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


class ExtensionSecurityValidator:

    def __init__(self, config: FileSecurityConfig):
        self.config = config

    def validate_extensions(self, filename: str) -> None:
        # Check for compound dangerous extensions first (e.g., .tar.xz, .user.js)
        filename_lower = filename.lower()
        for compound_ext in self.config.COMPOUND_BLOCKED_EXTENSIONS:
            if filename_lower.endswith(compound_ext):
                raise ValueError(
                    f"Dangerous compound file extension '{compound_ext}' detected in filename. Upload rejected for security."
                )

        # Check ALL extensions in the filename for dangerous ones
        parts = filename.split(".")
        if len(parts) > 1:
            for i in range(1, len(parts)):
                if f".{parts[i].lower()}" in self.config.BLOCKED_EXTENSIONS:
                    raise ValueError(
                        f"Dangerous file extension '.{parts[i].lower()}' detected in filename. Upload rejected for security."
                    )


class WindowsSecurityValidator:

    def __init__(self, config: FileSecurityConfig):
        self.config = config

    def validate_windows_reserved_names(self, filename: str) -> None:
        name_without_ext = os.path.splitext(filename)[0].lower().strip()
        # Remove leading dots to handle hidden files like ".CON.jpg"
        name_without_ext = name_without_ext.lstrip(".")
        # Remove trailing dots to handle cases like "con." or "con.."
        name_without_ext = name_without_ext.rstrip(".")

        if name_without_ext in self.config.WINDOWS_RESERVED_NAMES:
            raise ValueError(
                f"Filename '{filename}' uses Windows reserved name '{name_without_ext.upper()}'. "
                f"Reserved names: {', '.join(sorted(self.config.WINDOWS_RESERVED_NAMES)).upper()}"
            )


class CompressionSecurityValidator:

    def __init__(self, config: FileSecurityConfig):
        self.config = config

    def validate_zip_compression_ratio(
        self, file_content: bytes, compressed_size: int
    ) -> Tuple[bool, str]:
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
                    if (
                        uncompressed_size > self.config.limits.max_uncompressed_size // 10
                    ):  # Individual file limit
                        return (
                            False,
                            f"Individual file too large: '{entry.filename}' would expand to {uncompressed_size // (1024*1024)}MB",
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


class ZipContentInspector:

    def __init__(self, config: FileSecurityConfig):
        self.config = config

    def inspect_zip_content(self, file_content: bytes) -> Tuple[bool, str]:
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
        return (
            filename.startswith('/') or  # Unix absolute path
            filename.startswith('\\') or  # Windows UNC path
            (len(filename) > 1 and filename[1] == ':')  # Windows drive path
        )

    def _is_symlink(self, entry: zipfile.ZipInfo) -> bool:
        # Check if entry has symlink attributes
        return (entry.external_attr >> 16) & 0o120000 == 0o120000

    def _check_suspicious_patterns(self, filename: str) -> List[str]:
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
        ext = os.path.splitext(filename)[1].lower()
        
        for category in ZipThreatCategory:
            if category == ZipThreatCategory.NESTED_ARCHIVES:
                return ext in category.value
        
        return False

    def _inspect_entry_content(self, entry: zipfile.ZipInfo, zip_file: zipfile.ZipFile) -> List[str]:
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


class FileValidator:

    def __init__(self, config: FileSecurityConfig | None = None):
        self.config = config or FileSecurityConfig()

        # Initialize specialized validators
        self.unicode_validator = UnicodeSecurityValidator(self.config)
        self.extension_validator = ExtensionSecurityValidator(self.config)
        self.windows_validator = WindowsSecurityValidator(self.config)
        self.compression_validator = CompressionSecurityValidator(self.config)
        self.zip_inspector = ZipContentInspector(self.config)

        # Initialize python-magic for content-based detection
        try:
            self.magic_mime = magic.Magic(mime=True)
            self.magic_available = True
            core_logger.print_to_log(
                "File content detection (python-magic) initialized", "debug"
            )
        except Exception as err:
            self.magic_available = False
            core_logger.print_to_log(
                f"Warning: python-magic not available for content detection: {err}",
                "warning",
            )

    def _detect_mime_type(self, file_content: bytes, filename: str) -> str:
        detected_mime = None

        # Method 1: Content-based detection using python-magic (most reliable)
        if self.magic_available:
            try:
                detected_mime = self.magic_mime.from_buffer(file_content)
            except Exception as err:
                core_logger.print_to_log(
                    f"Magic MIME detection failed: {err}", "warning"
                )

        # Method 2: Fallback to filename-based detection
        if not detected_mime:
            detected_mime, _ = mimetypes.guess_type(filename)

        return detected_mime or "application/octet-stream"

    def _validate_file_signature(self, file_content: bytes, expected_type: str) -> bool:
        if len(file_content) < 4:
            return False

        # Common file signatures
        signatures = {
            "image": [
                b"\xff\xd8\xff",  # JPEG
                b"\xff\xd8\xff\xe1",  # JPEG EXIF (additional JPEG variant)
                b"\x89PNG\r\n\x1a\n",  # PNG
            ],
            "zip": [
                b"PK\x03\x04",  # ZIP file
                b"PK\x05\x06",  # Empty ZIP
                b"PK\x07\x08",  # ZIP with spanning
            ],
        }

        expected_signatures = signatures.get(expected_type, [])

        for signature in expected_signatures:
            if file_content.startswith(signature):
                return True

        return False

    def _sanitize_filename(self, filename: str) -> str:
        if not filename:
            raise ValueError("Filename cannot be empty")

        # Unicode security validation (must be first)
        # This detects and blocks Unicode-based attacks before any other processing
        try:
            filename = self.unicode_validator.validate_unicode_security(filename)
        except ValueError as err:
            raise err

        # Remove path components to prevent directory traversal
        filename = os.path.basename(filename)

        # Remove null bytes and control characters
        filename = "".join(
            char for char in filename if ord(char) >= 32 and char != "\x7f"
        )

        # Remove dangerous characters that could be used for path traversal or command injection
        dangerous_chars = '<>:"/\\|?*\x00'
        for char in dangerous_chars:
            filename = filename.replace(char, "_")

        # Check for Windows reserved names before any other processing
        # This must be done early to prevent reserved names from being created
        self.windows_validator.validate_windows_reserved_names(filename)

        # Handle compound and double extensions security risk
        # This also checks all dangerous extensions
        self.extension_validator.validate_extensions(filename)

        # Limit filename length (preserve extension)
        name_part, ext_part = os.path.splitext(filename)
        if len(name_part) > 100:
            name_part = name_part[:100]
            filename = name_part + ext_part

        # Ensure we don't end up with just an extension or empty name
        if not name_part or name_part.strip() == "":
            filename = f"file_{int(time.time())}{ext_part}"

        # Final check: ensure the sanitized filename doesn't become a reserved name
        self.windows_validator.validate_windows_reserved_names(filename)

        core_logger.print_to_log(
            f"Filename sanitized: original='{os.path.basename(filename if filename else 'None')}' -> sanitized='{filename}'",
            "debug",
        )

        return filename

    def _validate_filename(self, file: UploadFile) -> Tuple[bool, str] | None:
        # Check filename
        if not file.filename:
            return False, "Filename is required"

        # Sanitize the filename to prevent security issues
        try:
            sanitized_filename = self._sanitize_filename(file.filename)

            # Update the file object with sanitized filename
            file.filename = sanitized_filename

            # Additional validation after sanitization
            if not sanitized_filename or sanitized_filename.strip() == "":
                return False, "Invalid filename after sanitization"
        except ValueError as err:
            # Dangerous extension detected - reject the file
            return False, str(err)
        except Exception as err:
            core_logger.print_to_log(
                f"Unexpected error during filename validation: {str(err)}", "error"
            )
            return False, "Filename validation failed due to internal error"

    def _validate_file_extension(
        self, file: UploadFile, allowed_extensions: Set[str]
    ) -> Tuple[bool, str] | None:
        # Check file extension
        if not file.filename:
            return False, "Filename is required for extension validation"

        _, ext = os.path.splitext(file.filename.lower())
        if ext not in allowed_extensions:
            return (
                False,
                f"Invalid file extension. Allowed: {', '.join(allowed_extensions)}",
            )

        # Check for blocked extensions
        if ext in self.config.BLOCKED_EXTENSIONS:
            return False, f"File extension {ext} is blocked for security reasons"

    async def _validate_file_size(
        self, file: UploadFile, max_file_size: int
    ) -> Tuple[bytes | None, int | None, bool, str]:
        # Read first chunk for content analysis
        file_content = await file.read(8192)  # Read first 8KB

        # Reset file position
        await file.seek(0)

        # Check file size
        file_size = len(file_content)
        if hasattr(file, "size") and file.size:
            file_size = file.size
        else:
            # Estimate size by reading the rest
            remaining = await file.read()
            file_size = len(file_content) + len(remaining)
            await file.seek(0)

        if file_size > max_file_size:
            return (
                None,
                None,
                False,
                f"File too large. File size: {file_size // (1024*1024)}MB, maximum: {max_file_size // (1024*1024)}MB",
            )

        if file_size == 0:
            return None, None, False, "Empty file not allowed"

        return file_content, file_size, True, "Passed"

    async def validate_image_file(self, file: UploadFile) -> Tuple[bool, str]:
        try:
            # Validate filename
            filename_validation = self._validate_filename(file)
            if filename_validation is not None:
                return filename_validation

            # Validate file extension
            extension_validation = self._validate_file_extension(
                file, self.config.ALLOWED_IMAGE_EXTENSIONS
            )
            if extension_validation is not None:
                return extension_validation

            # Validate file size
            size_validation = await self._validate_file_size(
                file, self.config.limits.max_image_size
            )
            if size_validation[0] is None:
                return size_validation[2], size_validation[3]

            # Detect MIME type
            filename = file.filename or "unknown"
            detected_mime = self._detect_mime_type(size_validation[0], filename)

            if detected_mime not in self.config.ALLOWED_IMAGE_MIMES:
                return (
                    False,
                    f"Invalid file type. Detected: {detected_mime}. Allowed: {', '.join(self.config.ALLOWED_IMAGE_MIMES)}",
                )

            # Validate file signature
            if not self._validate_file_signature(size_validation[0], "image"):
                return False, "File content does not match expected image format"

            core_logger.print_to_log(
                f"Image file validation passed: {filename} ({detected_mime}, {size_validation[1]} bytes)",
                "debug",
            )

            return True, "Validation successful"
        except Exception as err:
            core_logger.print_to_log(
                f"Error during image file validation: {err}", "error", exc=err
            )
            return False, "File validation failed due to internal error"

    async def validate_zip_file(self, file: UploadFile) -> Tuple[bool, str]:
        try:
            # Validate filename
            filename_validation = self._validate_filename(file)
            if filename_validation is not None:
                return filename_validation

            # Validate file extension
            extension_validation = self._validate_file_extension(
                file, self.config.ALLOWED_ZIP_EXTENSIONS
            )
            if extension_validation is not None:
                return extension_validation

            # Validate file size
            size_validation = await self._validate_file_size(
                file, self.config.limits.max_zip_size
            )
            if size_validation[0] is None:
                return size_validation[2], size_validation[3]

            # Detect MIME type
            filename = file.filename or "unknown"
            detected_mime = self._detect_mime_type(size_validation[0], filename)

            if detected_mime not in self.config.ALLOWED_ZIP_MIMES:
                return (
                    False,
                    f"Invalid file type. Detected: {detected_mime}. Expected ZIP file.",
                )

            # Validate ZIP file signature
            if not self._validate_file_signature(size_validation[0], "zip"):
                return False, "File content does not match ZIP format"

            # Validate ZIP compression ratio to detect zip bombs
            # size_validation[1] is guaranteed to be int here since size_validation[0] is not None
            file_size = size_validation[1]
            if file_size is not None:
                compression_validation = (
                    self.compression_validator.validate_zip_compression_ratio(
                        size_validation[0], file_size
                    )
                )
                if not compression_validation[0]:
                    return (
                        False,
                        f"ZIP compression validation failed: {compression_validation[1]}",
                    )

            # Perform ZIP content inspection if enabled
            if self.config.limits.scan_zip_content:
                content_inspection = self.zip_inspector.inspect_zip_content(
                    size_validation[0]
                )
                if not content_inspection[0]:
                    return (
                        False,
                        f"ZIP content inspection failed: {content_inspection[1]}",
                    )

            core_logger.print_to_log(
                f"ZIP file validation passed: {filename} ({detected_mime}, {size_validation[1]} bytes)",
                "debug",
            )

            return True, "Validation successful"
        except ValueError as err:
            # Dangerous extension detected - reject the file
            return False, str(err)
        except Exception as err:
            core_logger.print_to_log(
                f"Error during ZIP file validation: {err}", "error", exc=err
            )
            return False, "File validation failed due to internal error"


# Global validator instance
file_validator = FileValidator()


async def validate_profile_image_upload(file: UploadFile) -> None:
    is_valid, error_message = await file_validator.validate_image_file(file)

    if not is_valid:
        core_logger.print_to_log(
            f"Profile image upload validation failed: {error_message}", "warning"
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid image file: {error_message}",
        )


async def validate_profile_data_upload(file: UploadFile) -> None:
    is_valid, error_message = await file_validator.validate_zip_file(file)

    if not is_valid:
        core_logger.print_to_log(
            f"Profile data upload validation failed: {error_message}", "warning"
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid ZIP file: {error_message}",
        )


def get_secure_filename(original_filename: str) -> str:
    try:
        return file_validator._sanitize_filename(original_filename)
    except ValueError as err:
        raise err
    except Exception as err:
        core_logger.print_to_log(
            f"Error during filename sanitization: {err}", "error", exc=err
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal Server Error during filename sanitization",
        ) from err


# Perform configuration validation when module is imported
# This ensures configuration issues are caught early during application startup
try:
    FileSecurityConfig.validate_and_report(strict=False)
    core_logger.print_to_log("File security configuration validation completed successfully", "info")
except Exception as validation_error:
    core_logger.print_to_log(
        f"File security configuration validation encountered issues: {validation_error}", 
        "warning"
    )
