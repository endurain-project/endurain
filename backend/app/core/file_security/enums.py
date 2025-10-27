"""Enumeration classes for categorizing security threats and patterns."""

from enum import Enum


class DangerousExtensionCategory(Enum):
    """
    File extension categories considered potentially dangerous for uploads.

    Attributes:
        WINDOWS_EXECUTABLES: Traditional Windows executable formats.
        SCRIPT_FILES: Script files that can execute code.
        WEB_SCRIPTS: Web server and dynamic content scripts.
        UNIX_EXECUTABLES: Unix/Linux executables and shell scripts.
        MACOS_EXECUTABLES: macOS specific executables and applications.
        JAVA_EXECUTABLES: Java related executables and bytecode.
        MOBILE_APPS: Mobile application packages.
        BROWSER_EXTENSIONS: Browser extensions and web applications.
        PACKAGE_FORMATS: Modern package managers and distribution formats.
        ARCHIVE_FORMATS: Archive formats that can contain executables.
        VIRTUALIZATION_FORMATS: Virtualization and container formats.
        OFFICE_MACROS: Office documents with macro capabilities.
        SYSTEM_FILES: System shortcuts and configuration files.
        SYSTEM_DRIVERS: System drivers and low-level components.
        WINDOWS_THEMES: Windows theme and customization files.
        HELP_FILES: Help and documentation files that can execute code.
    """

    # Traditional Windows executables
    WINDOWS_EXECUTABLES = {
        ".exe",
        ".bat",
        ".cmd",
        ".com",
        ".pif",
        ".scr",
        ".msi",
        ".dll",
    }

    # Script files that can execute code
    SCRIPT_FILES = {
        ".vbs",
        ".js",
        ".jse",
        ".wsf",
        ".wsh",
        ".hta",
        ".ps1",
        ".psm1",
        ".ps1xml",
        ".psc1",
        ".psd1",
        ".pssc",
        ".cdxml",
        ".xaml",
    }

    # Web server and dynamic content scripts
    WEB_SCRIPTS = {
        ".jsp",
        ".php",
        ".php3",
        ".php4",
        ".php5",
        ".phtml",
        ".asp",
        ".aspx",
        ".cer",
        ".cgi",
        ".pl",
        ".py",
        ".rb",
        ".go",
        ".lua",
    }

    # Unix/Linux executables and shell scripts
    UNIX_EXECUTABLES = {
        ".sh",
        ".bash",
        ".zsh",
        ".fish",
        ".csh",
        ".ksh",
        ".tcsh",
        ".run",
        ".bin",
        ".out",
        ".elf",
        ".so",
        ".a",
    }

    # macOS specific executables and applications
    MACOS_EXECUTABLES = {
        ".app",
        ".dmg",
        ".pkg",
        ".mpkg",
        ".command",
        ".tool",
        ".workflow",
        ".action",
        ".dylib",
        ".bundle",
        ".framework",
    }

    # Java related executables and bytecode
    JAVA_EXECUTABLES = {".jar", ".war", ".ear", ".jnlp", ".class"}

    # Mobile application packages
    MOBILE_APPS = {".apk", ".aab", ".ipa", ".appx", ".msix", ".xap"}

    # Browser extensions and web applications
    BROWSER_EXTENSIONS = {
        ".crx",
        ".xpi",
        ".safariextz",
        ".oex",
        ".nex",
        ".gadget",
    }

    # Modern package managers and distribution formats
    PACKAGE_FORMATS = {
        ".deb",
        ".rpm",
        ".snap",
        ".flatpak",
        ".appimage",
        ".vsix",
        ".nupkg",
        ".gem",
        ".whl",
        ".egg",
    }

    # Archive formats that can contain executables
    ARCHIVE_FORMATS = {
        ".7z",
        ".rar",
        ".cab",
        ".ace",
        ".arj",
        ".lzh",
        ".lha",
        ".zoo",
    }

    # Virtualization and container formats
    VIRTUALIZATION_FORMATS = {
        ".ova",
        ".ovf",
        ".vmdk",
        ".vdi",
        ".vhd",
        ".vhdx",
        ".qcow2",
        ".docker",
    }

    # Office documents with macro capabilities
    OFFICE_MACROS = {
        ".docm",
        ".dotm",
        ".xlsm",
        ".xltm",
        ".xlam",
        ".pptm",
        ".potm",
        ".ppam",
        ".sldm",
    }

    # System shortcuts and configuration files
    SYSTEM_FILES = {
        ".url",
        ".website",
        ".webloc",
        ".desktop",
        ".lnk",
        ".application",
        ".manifest",
        ".deploy",
        ".msu",
        ".patch",
        ".diff",
        ".reg",
        ".inf",
    }

    # System drivers and low-level components
    SYSTEM_DRIVERS = {".sys", ".drv", ".ocx", ".cpl"}

    # Windows theme and customization files
    WINDOWS_THEMES = {
        ".theme",
        ".themepack",
        ".scf",
        ".shs",
        ".shb",
        ".sct",
        ".ws",
        ".job",
        ".msc",
    }

    # Help and documentation files that can execute code
    HELP_FILES = {".chm", ".hlp"}


class CompoundExtensionCategory(Enum):
    """
    Categorized compound file extensions that combine multiple suffixes.

    Attributes:
        COMPRESSED_ARCHIVES: Multi-part archive formats.
        JAVASCRIPT_VARIANTS: Specialized JavaScript files.
        WEB_CONTENT: Minified static web assets.
    """

    # Compressed archive formats
    COMPRESSED_ARCHIVES = {
        ".tar.xz",
        ".tar.gz",
        ".tar.bz2",
        ".tar.lz",
        ".tar.lzma",
        ".tar.Z",
        ".tgz",
        ".tbz2",
    }

    # JavaScript related compound extensions
    JAVASCRIPT_VARIANTS = {".user.js", ".backup.js", ".min.js", ".worker.js"}

    # Web content compound extensions
    WEB_CONTENT = {".min.css", ".min.html"}


class UnicodeAttackCategory(Enum):
    """
    Categorized Unicode code points used in obfuscation attacks.

    Attributes:
        DIRECTIONAL_OVERRIDES: Right-to-left and directional controls.
        ZERO_WIDTH_CHARACTERS: Zero-width and invisible characters.
        LANGUAGE_MARKS: Language and format specific characters.
        CONFUSING_PUNCTUATION: Punctuation that can disguise extensions.
    """

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
    """
    Categorized patterns used to flag potentially malicious uploads.

    Attributes:
        DIRECTORY_TRAVERSAL: Directory traversal attack patterns.
        SUSPICIOUS_NAMES: Suspicious filename patterns.
        EXECUTABLE_SIGNATURES: Dangerous file content signatures.
        SUSPICIOUS_PATHS: Suspicious path components.
    """

    # Directory traversal attack patterns
    DIRECTORY_TRAVERSAL = {
        "../",
        "..\\",
        ".../",
        "...\\",
        "....//",
        "....\\\\",
        "%2e%2e%2f",
        "%2e%2e%5c",  # URL encoded ../ and ..\
        "%252e%252e%252f",
        "%252e%252e%255c",  # Double URL encoded
    }

    # Suspicious filename patterns
    SUSPICIOUS_NAMES = {
        # Windows system files that shouldn't be in user uploads
        "autorun.inf",
        "desktop.ini",
        "thumbs.db",
        ".ds_store",
        # Common malware names
        "install.exe",
        "setup.exe",
        "update.exe",
        "patch.exe",
        "crack.exe",
        "keygen.exe",
        "loader.exe",
        "activator.exe",
        # Hidden or system-like files
        ".htaccess",
        ".htpasswd",
        "web.config",
        "robots.txt",
    }

    # Dangerous file content signatures (magic bytes)
    EXECUTABLE_SIGNATURES = {
        # Windows PE executables
        b"MZ",
        b"PE\x00\x00",
        # ELF executables (Linux)
        b"\x7fELF",
        # Mach-O executables (macOS)
        b"\xfe\xed\xfa\xce",
        b"\xfe\xed\xfa\xcf",
        b"\xce\xfa\xed\xfe",
        b"\xcf\xfa\xed\xfe",
        # Java class files
        b"\xca\xfe\xba\xbe",
        # Windows shortcuts (.lnk)
        b"L\x00\x00\x00",
    }

    # Suspicious path components
    SUSPICIOUS_PATHS = {
        # Windows system directories
        "windows/",
        "system32/",
        "syswow64/",
        "programfiles/",
        # Unix system directories
        "/bin/",
        "/sbin/",
        "/usr/bin/",
        "/usr/sbin/",
        "/etc/",
        # Web server directories
        "cgi-bin/",
        "htdocs/",
        "www/",
        "wwwroot/",
        # Development/build directories
        ".git/",
        ".svn/",
        "node_modules/",
        "__pycache__/",
    }


class ZipThreatCategory(Enum):
    """
    Categories of potentially harmful contents within ZIP archives.

    Attributes:
        NESTED_ARCHIVES: Archive format threats.
        EXECUTABLE_FILES: Executable content threats.
        SCRIPT_FILES: Script and code threats.
        SYSTEM_FILES: System and configuration threats.
    """

    # Archive format threats
    NESTED_ARCHIVES = {
        ".zip",
        ".rar",
        ".7z",
        ".tar",
        ".gz",
        ".bz2",
        ".xz",
        ".tar.gz",
        ".tar.bz2",
        ".tar.xz",
        ".tgz",
        ".tbz2",
    }

    # Executable content threats
    EXECUTABLE_FILES = {
        ".exe",
        ".com",
        ".bat",
        ".cmd",
        ".scr",
        ".pif",
        ".bin",
        ".run",
        ".app",
        ".deb",
        ".rpm",
        ".msi",
    }

    # Script and code threats
    SCRIPT_FILES = {
        ".js",
        ".vbs",
        ".ps1",
        ".sh",
        ".bash",
        ".py",
        ".php",
        ".pl",
        ".rb",
        ".lua",
        ".asp",
        ".jsp",
    }

    # System and configuration threats
    SYSTEM_FILES = {
        ".dll",
        ".so",
        ".dylib",
        ".sys",
        ".drv",
        ".inf",
        ".reg",
        ".cfg",
        ".conf",
        ".ini",
    }
