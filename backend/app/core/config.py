"""Application configuration.

Environment-driven values are loaded into a single
:class:`Settings` instance backed by ``pydantic-settings``.
This gives us typed access, declarative validation,
``.env`` file support, and a single override point for
tests.

Module-level constants are kept (``LOG_LEVEL``,
``ENDURAIN_HOST``, ``DATA_DIR``, …) as thin aliases to
``settings.X`` so that existing call sites
(``core_config.LOG_LEVEL``, etc.) and existing test
mocks (``mock.patch("...core_config.ATTR")``) keep
working unchanged.
"""

import ipaddress
import os
import stat
import threading
from pathlib import Path
from tempfile import gettempdir
from typing import Annotated, Self

from cryptography.fernet import Fernet
from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

import core.logger as core_logger
import core.network as core_network
import core.redis as core_redis

# Pure constants — neither env-driven nor derived from settings.
API_VERSION = "v0.19.1"
LICENSE_NAME = "GNU Affero General Public License v3.0 or later"
LICENSE_IDENTIFIER = "AGPL-3.0-or-later"
LICENSE_URL = "https://spdx.org/licenses/AGPL-3.0-or-later.html"
ROOT_PATH = "/api/v1"

USER_IMAGES_URL_PATH = "user_images"
SERVER_IMAGES_URL_PATH = "server_images"

STRAVA_BULK_IMPORT_ACTIVITIES_FILE = "activities.csv"
STRAVA_BULK_IMPORT_BIKES_FILE = "bikes.csv"
STRAVA_BULK_IMPORT_SHOES_FILE = "shoes.csv"
STRAVA_BULK_IMPORT_SHOES_UNNAMED_SHOE = "Unnamed Shoe "

SUPPORTED_FILE_FORMATS = [
    ".fit",
    ".gpx",
    ".tcx",
    ".gz",
]  # used to screen bulk import files


# Settings — every value driven by an environment variable.
class Settings(BaseSettings):
    """Environment-driven configuration values.

    Field names mirror their environment variable names
    so the existing ``ENDURAIN_HOST``, ``LOG_LEVEL``, …
    contract is preserved end-to-end.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )

    # --- Logging / environment ---
    LOG_LEVEL: str = "info"
    ENVIRONMENT: str = "production"
    TZ: str = "UTC"

    # --- Host / redirects ---
    ENDURAIN_HOST: str = "http://localhost:8080"
    # NoDecode disables the default JSON pre-parsing for
    # complex types so the validators below see the raw
    # comma-separated env value (e.g. "a,b,c") rather than
    # JSON. Without this pydantic-settings would attempt
    # ``json.loads`` first and raise on plain strings.
    ALLOWED_REDIRECT_SCHEMES: Annotated[set[str], NoDecode] = {"endurain"}
    TRUSTED_PROXIES: Annotated[list[str], NoDecode] = []
    # Narrow SSRF exception list for admin-configured
    # outbound calls (currently OIDC discovery / JWKS).
    # Accepts exact hostnames (case-insensitive) and
    # explicit IPv4/IPv6 CIDRs. Wildcards and overly
    # broad ranges (IPv4 prefix < 8, IPv6 prefix < 32)
    # are rejected at startup to prevent accidental
    # neutering of the SSRF guard.
    SSRF_ALLOWED_HOSTS: Annotated[list[str], NoDecode] = []
    # Extra origins appended to the Content-Security-Policy
    # ``connect-src`` directive. Needed when Endurain runs
    # behind a forward-auth reverse proxy (e.g. Pangolin)
    # that redirects API calls to its own domain for session
    # validation; without its origin here the browser blocks
    # the redirect. Comma-separated CSP source expressions
    # (e.g. "https://auth.example.com"). Overly broad values
    # (bare "*", scheme-only "https:") are dropped at startup
    # because they would defeat the connect-src protection.
    CSP_ADDITIONAL_CONNECT_SRC: Annotated[list[str], NoDecode] = []

    # --- Internal caches (populated at startup) ---
    # Hostnames from TRUSTED_PROXIES, resolved to IPs at startup and cached.
    # Used by _is_trusted_peer() to check resolved hostname IPs.
    _resolved_trusted_proxy_ips: set[str] = set()

    # --- Filesystem layout ---
    FRONTEND_DIR: str = "/app/frontend/dist"
    BACKEND_DIR: str = "/app/backend"
    DATA_DIR: str = ""
    LOGS_DIR: str = ""
    FILES_DIR: str = ""
    ACTIVITY_MEDIA_DIR: str = ""
    ACTIVITY_THUMBNAILS_DIR: str = ""

    # --- Rate limiting ---
    RATE_LIMIT_ENABLED: bool = True
    RATE_LIMIT_STORAGE_URI: str = "memory://"
    AUTH_SECURITY_STORAGE_URI: str | None = None

    # --- API key delivery ---
    # Allow API keys to be passed as a ``?api_key=`` query parameter.
    # Disabled by default because query-string credentials appear in
    # access logs, proxy histories, and browser history.
    # Enable only if you have integrations that cannot set custom headers.
    ALLOW_API_KEY_QUERY_PARAM: bool = False

    # --- Reverse-geocoding providers ---
    REVERSE_GEO_PROVIDER: str = "nominatim"
    PHOTON_API_HOST: str = "photon.komoot.io"
    PHOTON_API_USE_HTTPS: bool = True
    NOMINATIM_API_HOST: str = "nominatim.openstreetmap.org"
    NOMINATIM_API_USE_HTTPS: bool = True
    GEOCODES_MAPS_API: str = "changeme"
    REVERSE_GEO_RATE_LIMIT: float = 1.0

    # --- Email (SMTP) ---
    # SMTP_PASSWORD is read separately via ``read_secret``
    # so it inherits the Docker-secrets ``_FILE`` contract
    # used by DB_PASSWORD / SECRET_KEY / FERNET_KEY and is
    # never materialised into Settings (kept out of any
    # accidental ``settings.dict()`` dump).
    SMTP_HOST: str | None = None
    SMTP_PORT: int = 587
    SMTP_USERNAME: str | None = None
    # SMTP_FROM sets the "From" address on outgoing email.
    # When unset, Apprise auto-detects it from the URL
    # (typically SMTP_USERNAME). Providers that enforce a
    # verified sender (e.g. Brevo) require this to match an
    # approved sender address, which may differ from the
    # SMTP auth username.
    SMTP_FROM: str | None = None
    SMTP_SECURE: bool = True
    SMTP_SECURE_TYPE: str = "starttls"

    # ----- Validators -----

    @field_validator("LOG_LEVEL", "ENVIRONMENT", mode="before")
    @classmethod
    def _to_lower(cls, v: str) -> str:
        return v.lower() if isinstance(v, str) else v

    @field_validator("PHOTON_API_HOST", "NOMINATIM_API_HOST", mode="before")
    @classmethod
    def _host_lower(cls, v: str) -> str:
        return v.lower() if isinstance(v, str) else v

    @field_validator("SMTP_SECURE_TYPE", mode="before")
    @classmethod
    def _smtp_secure_type_lower(cls, v):
        """Normalise to lower-case and validate against the
        small allow-list Apprise understands (``starttls``,
        ``ssl``). Falls back to ``starttls`` on garbage input
        with a warning instead of failing startup.
        """
        if v is None or v == "":
            return "starttls"
        if not isinstance(v, str):
            return "starttls"
        normalised = v.lower().strip()
        if normalised not in ("starttls", "ssl"):
            core_logger.print_to_log_and_console(
                "Invalid SMTP_SECURE_TYPE value, expected 'starttls' or 'ssl'; defaulting to 'starttls'",
                "warning",
            )
            return "starttls"
        return normalised

    @field_validator("ALLOWED_REDIRECT_SCHEMES", mode="before")
    @classmethod
    def _parse_allowed_schemes(cls, v):
        """Accept comma-separated env value or already-parsed iterable."""
        if v is None or v == "":
            return set()
        if isinstance(v, str):
            return {s.strip().lower() for s in v.split(",") if s.strip()}
        return {str(s).strip().lower() for s in v if str(s).strip()}

    @field_validator("TRUSTED_PROXIES", mode="before")
    @classmethod
    def _parse_trusted_proxies(cls, v):
        """Accept comma-separated env value or already-parsed iterable."""
        if v is None or v == "":
            return []
        if isinstance(v, str):
            return [ip.strip() for ip in v.split(",") if ip.strip()]
        return v

    @field_validator("TRUSTED_PROXIES", mode="after")
    @classmethod
    def _validate_trusted_proxies(cls, v):
        """Validate TRUSTED_PROXIES entries are valid IPs, CIDRs, hostnames, or '*'.

        Entries may be:
        - Exact IPs (IPv4 or IPv6)
        - CIDR ranges (e.g., 10.0.0.0/8)
        - Hostnames (e.g., proxy.internal, caddy)
        - Wildcard '*' (trusts all peers)

        Invalid entries are rejected with a ValidationError.
        Hostnames are not resolved at config validation time;
        resolution happens at startup in Phase 2.
        """

        for entry in v:
            entry = entry.strip()
            if not entry:
                continue

            # Wildcard is allowed
            if entry == "*":
                continue

            # Try to parse as IP or CIDR
            if core_network._looks_like_ip(entry) or "/" in entry:
                try:
                    ipaddress.ip_network(entry, strict=False)
                    continue
                except ValueError as err:
                    raise ValueError(
                        f"Invalid TRUSTED_PROXIES entry '{entry}': not a valid IP address or CIDR range."
                    ) from err

            # Hostname: validate RFC 1123 syntax before accepting.
            else:
                if not core_network._is_valid_hostname(entry):
                    raise ValueError(f"Invalid TRUSTED_PROXIES entry '{entry}': not a valid hostname.")

        return v

    @field_validator("CSP_ADDITIONAL_CONNECT_SRC", mode="before")
    @classmethod
    def _parse_csp_additional_connect_src(cls, v):
        """Parse the extra CSP ``connect-src`` origins.

        Accepts a comma-separated env value or an already
        parsed iterable. Entries are dropped with a warning
        (rather than failing startup) when they are unsafe:

        - Containing whitespace or ``;`` would let a value
          break out of the directive (header injection).
        - The bare wildcard ``*`` would allow connections to
          any origin and defeats the connect-src control. Host
          wildcards like ``https://*.example.com`` are kept.
        - Scheme-only sources (``https:``, ``ws:``, ...) allow
          any host on that scheme and are similarly too broad.
        """
        if v is None or v == "":
            return []
        raw_entries = [e.strip() for e in v.split(",")] if isinstance(v, str) else [str(e).strip() for e in v]

        cleaned: list[str] = []
        for entry in raw_entries:
            if not entry:
                continue
            if ";" in entry or any(c.isspace() for c in entry):
                core_logger.print_to_log_and_console(
                    f"Ignoring invalid CSP_ADDITIONAL_CONNECT_SRC entry '{entry}': must not contain whitespace or ';'.",
                    "warning",
                )
                continue
            if entry == "*":
                core_logger.print_to_log_and_console(
                    "Ignoring wildcard '*' in CSP_ADDITIONAL_CONNECT_SRC: it would allow "
                    "connections to any origin and defeats the connect-src protection.",
                    "warning",
                )
                continue
            # Scheme-only sources (e.g. "https:", "ws:") end in ':' with no host
            # and allow any host on that scheme — too broad for an allowlist.
            if entry.endswith(":") and "/" not in entry:
                core_logger.print_to_log_and_console(
                    f"Ignoring scheme-only CSP_ADDITIONAL_CONNECT_SRC entry '{entry}': "
                    "it allows any host on that scheme and is too broad for connect-src.",
                    "warning",
                )
                continue
            cleaned.append(entry)
        return cleaned

    @field_validator("SSRF_ALLOWED_HOSTS", mode="before")
    @classmethod
    def _parse_ssrf_allowed_hosts(cls, v):
        """Parse and validate the SSRF allowlist.

        Accepts a comma-separated env value or an already
        parsed iterable. Entries may be:

        - Exact hostnames (e.g. ``auth.example.com``).
          Lower-cased and stripped of any URL scheme,
          path, or port (only the host label is kept).
        - Explicit CIDRs (e.g. ``10.10.0.0/24`` or
          ``fd00::/64``). The prefix length must be
          tight enough to be auditable: IPv4 ``>= 8``
          and IPv6 ``>= 32``.

        Rejects:

        - Wildcards (``*`` or empty entries).
        - ``0.0.0.0/0`` / ``::/0`` and any range broader
          than the limits above.

        Invalid entries are dropped with a warning so a
        single typo does not block startup, but at least
        one valid entry must remain for the field to
        take effect.
        """

        if v is None or v == "":
            return []
        raw_entries = [e.strip() for e in v.split(",")] if isinstance(v, str) else [str(e).strip() for e in v]

        cleaned: list[str] = []
        for entry in raw_entries:
            if not entry or entry == "*":
                if entry == "*":
                    core_logger.print_to_log_and_console(
                        "Ignoring wildcard '*' entry in SSRF_ALLOWED_HOSTS (not permitted).",
                        "warning",
                    )
                continue

            # CIDR / IP entry
            if "/" in entry or core_network._looks_like_ip(entry):
                try:
                    network = ipaddress.ip_network(entry, strict=False)
                except ValueError:
                    core_logger.print_to_log_and_console(
                        f"Ignoring invalid SSRF_ALLOWED_HOSTS entry '{entry}': not a valid IP or CIDR.",
                        "warning",
                    )
                    continue
                min_prefix = 8 if network.version == 4 else 32
                if network.prefixlen < min_prefix:
                    core_logger.print_to_log_and_console(
                        f"Ignoring overly broad SSRF_ALLOWED_HOSTS "
                        f"entry '{entry}': prefix /{network.prefixlen} "
                        f"is wider than the minimum /{min_prefix} for "
                        f"IPv{network.version}.",
                        "warning",
                    )
                    continue
                cleaned.append(str(network))
                continue

            # Hostname entry — strip scheme/port/path
            host = entry.lower()
            if "://" in host:
                host = host.split("://", 1)[1]
            host = host.split("/", 1)[0]
            if host.startswith("["):  # IPv6 literal w/ optional :port
                bracket = host.find("]")
                if bracket != -1:
                    host = host[1:bracket]
            elif ":" in host and host.count(":") == 1:
                host = host.split(":", 1)[0]
            if not host:
                core_logger.print_to_log_and_console(
                    f"Ignoring empty SSRF_ALLOWED_HOSTS hostname from entry '{entry}'.",
                    "warning",
                )
                continue
            cleaned.append(host)

        return cleaned

    @field_validator("REVERSE_GEO_RATE_LIMIT", mode="before")
    @classmethod
    def _parse_geo_rate(cls, v):
        """Tolerate non-numeric strings instead of failing startup."""
        if v is None or v == "":
            return 1.0
        try:
            return float(v)
        except (TypeError, ValueError):
            core_logger.print_to_log_and_console(
                "Invalid REVERSE_GEO_RATE_LIMIT value, expected a number; defaulting to 1.0",
                "warning",
            )
            return 1.0

    @model_validator(mode="after")
    def _fill_filesystem_defaults(self) -> Self:
        """Derive directory defaults from BACKEND_DIR when not explicit."""
        if not self.DATA_DIR:
            self.DATA_DIR = f"{self.BACKEND_DIR}/data"
        if not self.LOGS_DIR:
            self.LOGS_DIR = f"{self.BACKEND_DIR}/logs"
        if not self.FILES_DIR:
            self.FILES_DIR = f"{self.DATA_DIR}/activity_files"
        if not self.ACTIVITY_MEDIA_DIR:
            self.ACTIVITY_MEDIA_DIR = f"{self.DATA_DIR}/activity_media"
        if not self.ACTIVITY_THUMBNAILS_DIR:
            self.ACTIVITY_THUMBNAILS_DIR = f"{self.DATA_DIR}/activity_thumbnails"
        if not self.TRUSTED_PROXIES and self.ENVIRONMENT == "development" and "TRUSTED_PROXIES" not in os.environ:
            self.TRUSTED_PROXIES = ["*"]
        return self

    @property
    def resolved_auth_security_storage_uri(self) -> str:
        """Effective storage URI for auth-security and MFA stores.

        Resolves the precedence shared by the auth security stores, MFA
        setup-secret store, and Garmin MFA code store:
        ``AUTH_SECURITY_STORAGE_URI`` overrides ``RATE_LIMIT_STORAGE_URI``,
        falling back to ``memory://`` when neither is set.
        """
        return self.AUTH_SECURITY_STORAGE_URI or self.RATE_LIMIT_STORAGE_URI or "memory://"

    @model_validator(mode="after")
    def _warn_on_memory_security_storage(self) -> Self:
        """Warn when production-like auth protections are process-local."""
        if self.ENVIRONMENT == "development":
            return self

        if self.RATE_LIMIT_ENABLED and core_redis.is_memory_storage_uri(self.RATE_LIMIT_STORAGE_URI):
            core_logger.print_to_log_and_console(
                "RATE_LIMIT_STORAGE_URI uses process-local memory outside "
                "development. API rate-limit counters are not shared "
                "across workers; use Redis for multi-worker deployments.",
                "warning",
            )

        if core_redis.is_memory_storage_uri(self.resolved_auth_security_storage_uri):
            core_logger.print_to_log_and_console(
                "AUTH_SECURITY_STORAGE_URI resolves to process-local "
                "memory outside development. Login lockout and pending "
                "MFA state, including setup secrets, are not shared "
                "across workers; use Redis for multi-worker deployments.",
                "warning",
            )

        return self


settings = Settings()


# Derived module-level paths and runtime state.
USER_IMAGES_DIR = f"{settings.DATA_DIR}/{USER_IMAGES_URL_PATH}"
SERVER_IMAGES_DIR = f"{settings.DATA_DIR}/{SERVER_IMAGES_URL_PATH}"

FILES_PROCESSED_DIR = f"{settings.FILES_DIR}/processed"
FILES_BULK_IMPORT_DIR = f"{settings.FILES_DIR}/bulk_import"
FILES_BULK_IMPORT_IMPORT_ERRORS_DIR = f"{FILES_BULK_IMPORT_DIR}/import_errors"
STRAVA_BULK_IMPORT_DIR = f"{settings.FILES_DIR}/strava_import"
STRAVA_BULK_IMPORT_ACTIVITIES_DIR = f"{STRAVA_BULK_IMPORT_DIR}/activities"
STRAVA_BULK_IMPORT_MEDIA_DIR = f"{STRAVA_BULK_IMPORT_DIR}/media"
STRAVA_BULK_IMPORT_IMPORT_ERRORS_DIR = f"{STRAVA_BULK_IMPORT_DIR}/import_errors"

REVERSE_GEO_MIN_INTERVAL = 1.0 / settings.REVERSE_GEO_RATE_LIMIT if settings.REVERSE_GEO_RATE_LIMIT > 0 else 0
REVERSE_GEO_LOCK = threading.Lock()
REVERSE_GEO_LAST_CALL = 0.0


# Secret loading and environment validation
def read_secret(
    env_var_name: str,
    default_value: str | None = None,
) -> str | None:
    """
    Read secret from environment variable or file.

    Args:
        env_var_name: Name of environment variable.
        default_value: Default value if not found.

    Returns:
        Secret value or default if not found.

    Raises:
        EnvironmentError: If secret file is unsafe or
            unreadable.
    """
    # First, try to get the value directly from environment variable
    env_value = os.environ.get(env_var_name)
    if env_value is not None:
        return env_value

    # If not found, try to get from _FILE variant
    file_env_var = f"{env_var_name}_FILE"
    file_path_str = os.environ.get(file_env_var)

    if file_path_str:
        try:
            file_path = Path(file_path_str).resolve()

            # Security: Validate file path to prevent path traversal
            if not _is_safe_path(file_path):
                core_logger.print_to_log_and_console(f"Unsafe file path detected for {file_env_var}", "error")
                raise OSError(f"Unsafe file path for {file_env_var}")

            # Check if file exists and is readable
            if not file_path.exists():
                core_logger.print_to_log_and_console(f"Secret file not found for {file_env_var}", "error")
                raise OSError(f"Secret file not found for {file_env_var}")

            if not file_path.is_file():
                core_logger.print_to_log_and_console(f"Secret path is not a file for {file_env_var}", "error")
                raise OSError(f"Secret path is not a file for {file_env_var}")

            # Security: Check file permissions (should not be world-readable)
            file_stat = file_path.stat()
            if file_stat.st_mode & stat.S_IROTH:
                core_logger.print_to_log_and_console(
                    f"Secret file is world-readable for {file_env_var}",
                    "warning",
                )

            # Security: limit file size to prevent memory exhaustion.
            if file_stat.st_size > 65536:  # 64KB
                core_logger.print_to_log_and_console(f"Secret file too large for {file_env_var}", "error")
                raise OSError(f"Secret file too large for {file_env_var}")

            # Read the secret file
            with file_path.open("r", encoding="utf-8") as secret_file:
                content = secret_file.read().strip()

                if content:
                    core_logger.print_to_log_and_console(
                        f"Successfully loaded secret from file for {env_var_name}",
                        "debug",
                    )
                    return content
                else:
                    core_logger.print_to_log_and_console(f"Secret file is empty for {file_env_var}", "warning")

        except (OSError, UnicodeDecodeError) as e:
            # Log error without exposing file path details
            core_logger.print_to_log_and_console(
                f"Error reading secret file for {file_env_var}: {type(e).__name__}",
                "error",
            )
            raise OSError(f"Error reading secret file for {file_env_var}") from e
        except Exception as e:
            core_logger.print_to_log_and_console(
                f"Unexpected error reading secret for {file_env_var}: {type(e).__name__}",
                "error",
            )
            raise OSError(f"Unexpected error reading secret for {file_env_var}") from e

    # If neither environment variable nor file is found, return default
    return default_value


def _is_safe_path(file_path: Path) -> bool:
    """
    Validate if file path is safe to access.

    Args:
        file_path: Path to validate.

    Returns:
        True if path is safe, False otherwise.
    """
    try:
        # Resolve symlinks so comparisons are consistent across platforms
        # (e.g. /var/run → /private/var/run on macOS).
        resolved = Path(str(file_path)).resolve()

        # Allow common Docker secrets locations (resolve them too so that
        # e.g. /var/run/secrets → /private/var/run/secrets on macOS).
        allowed_dirs = [
            Path("/run/secrets").resolve(),  # Standard Docker secrets mount point
            Path("/var/run/secrets").resolve(),  # Alternative Docker secrets location
            Path("/secrets").resolve(),  # Custom secrets directory
        ]

        # For development, also allow the system temp dir and cwd.
        if settings.ENVIRONMENT == "development":
            allowed_dirs.append(Path(gettempdir()).resolve())
            allowed_dirs.append(Path.cwd().resolve())

        return any(resolved == allowed or resolved.is_relative_to(allowed) for allowed in allowed_dirs)

    except (OSError, ValueError, TypeError):
        return False


def validate_fernet_key(fernet_key: str | None) -> bool:
    """
    Validate Fernet encryption key format.

    Args:
        fernet_key: Fernet key to validate.

    Returns:
        True if key is valid, False otherwise.
    """
    if not fernet_key:
        core_logger.print_to_log_and_console(
            "FERNET_KEY is not set or empty",
            "error",
        )
        return False

    try:
        # Attempt to create a Fernet cipher with the key
        fernet_key_bytes = fernet_key.encode("utf-8")
        Fernet(fernet_key_bytes)

        core_logger.print_to_log_and_console("FERNET_KEY validation successful", "debug")
        return True
    except ValueError as err:
        core_logger.print_to_log_and_console(
            f"FERNET_KEY validation failed: Invalid key format ({type(err).__name__})",
            "error",
        )
        return False
    except Exception as err:
        core_logger.print_to_log_and_console(
            f"FERNET_KEY validation failed: Unexpected error ({type(err).__name__})",
            "error",
        )
        return False


def validate_log_level(log_level: str) -> bool:
    """
    Validate log level string.

    Args:
        log_level: Log level to validate.

    Returns:
        True if log level is valid, False otherwise.
    """
    valid_levels = {"critical", "error", "warning", "info", "debug", "trace"}
    if log_level.lower() in valid_levels:
        return True
    else:
        allowed_values = ", ".join(sorted(valid_levels))
        core_logger.print_to_log_and_console(
            f"Log level '{log_level}' is invalid. Must be one of: {allowed_values}",
            "error",
        )
        return False


def check_required_env_vars():
    """
    Validate required environment variables are set.

    Raises:
        EnvironmentError: If required variables missing.
    """
    # Secrets that support both direct env vars and _FILE variants
    secret_vars = ["DB_PASSWORD", "SECRET_KEY", "FERNET_KEY"]

    # Non-secret required vars that must be set directly
    required_env_vars = [
        "ENDURAIN_HOST",
    ]

    # Email is optional but warn if not configured
    email_vars = ["SMTP_HOST", "SMTP_USERNAME", "SMTP_PASSWORD"]
    for var in email_vars:
        value = read_secret(var) if var == "SMTP_PASSWORD" else os.getenv(var)
        if not value:
            core_logger.print_to_log_and_console(
                f"Email not configured (missing: {var}). Password reset feature will not work.",
                "info",
            )

    # Check secret variables. Direct env var or _FILE must be present.
    for var in secret_vars:
        file_var = f"{var}_FILE"
        if var not in os.environ and file_var not in os.environ:
            message = f"Missing required environment variable: {var} (or {file_var} for Docker secrets)"
            core_logger.print_to_log_and_console(
                message,
                "error",
            )
            raise OSError(message)

    # Check non-secret required variables
    for var in required_env_vars:
        if var not in os.environ:
            message = f"Missing required environment variable: {var}"
            core_logger.print_to_log_and_console(
                message,
                "error",
            )
            raise OSError(message)

    # Validate FERNET_KEY if it's available
    fernet_key = read_secret("FERNET_KEY")
    if fernet_key:
        is_valid = validate_fernet_key(fernet_key)
        if not is_valid:
            message = "FERNET_KEY validation failed. Please check the key format and regenerate if necessary."
            core_logger.print_to_log_and_console(
                message,
                "warning",
            )
            raise ValueError(message)

    validate_log_level(settings.LOG_LEVEL)


# Environment variables retired in v0.19.x. Maps the removed variable name to a
# short, actionable remediation string. These are validated by
# ``check_deprecated_env_vars`` at startup: because ``Settings`` uses
# ``extra="ignore"``, a stale value would otherwise be silently dropped, leaving
# the operator with no feedback that their configuration no longer takes effect.
DEPRECATED_ENV_VARS: dict[str, str] = {
    "UID": (
        "no longer used. The container runs as a fixed non-root 'app' user. "
        "For a custom UID/GID set 'user: \"<UID>:<GID>\"' in docker-compose and "
        "chown the host bind mounts accordingly."
    ),
    "GID": (
        "no longer used. The container runs as a fixed non-root 'app' user. "
        "For a custom UID/GID set 'user: \"<UID>:<GID>\"' in docker-compose and "
        "chown the host bind mounts accordingly."
    ),
    "FRONTEND_PROTOCOL": (
        "removed. ENVIRONMENT is now the single source of truth for the cookie "
        "'Secure' flag across login, refresh, and SSO. Use ENVIRONMENT=production "
        "(or demo) to serve over HTTPS."
    ),
}


def check_deprecated_env_vars() -> None:
    """
    Abort startup when retired environment variables are still set.

    Variables removed in v0.19.x are silently ignored by ``Settings``
    (``extra="ignore"``), so a leftover value would give the operator no
    feedback. Every offending variable is collected and reported together
    so the deployment can be fixed in a single pass rather than one restart
    at a time.

    Raises:
        EnvironmentError: If any deprecated variable is present in the
            process environment.
    """
    found = [name for name in DEPRECATED_ENV_VARS if name in os.environ]
    if not found:
        return

    core_logger.print_to_log_and_console(
        "Deprecated environment variable(s) detected. Endurain will not start "
        "until they are removed from your configuration:",
        "error",
    )
    for name in found:
        core_logger.print_to_log_and_console(
            f"  - {name}: {DEPRECATED_ENV_VARS[name]}",
            "error",
        )

    message = (
        f"Deprecated environment variable(s) in use: {', '.join(found)}. "
        "Remove them and restart. See "
        "https://docs.endurain.com/getting-started/advanced-started/"
        "#supported-environment-variables"
    )
    raise OSError(message)


def check_required_dirs():
    """
    Ensure required directories exist and are valid.

    Raises:
        EnvironmentError: If directory is not valid.
    """
    required_dirs = [
        settings.DATA_DIR,
        USER_IMAGES_DIR,
        SERVER_IMAGES_DIR,
        settings.ACTIVITY_MEDIA_DIR,
        settings.ACTIVITY_THUMBNAILS_DIR,
        settings.FILES_DIR,
        FILES_PROCESSED_DIR,
        FILES_BULK_IMPORT_DIR,
        FILES_BULK_IMPORT_IMPORT_ERRORS_DIR,
        settings.LOGS_DIR,
    ]

    for required_dir in required_dirs:
        required_path = Path(required_dir)
        if not required_path.exists():
            required_path.mkdir(parents=True)
        elif not required_path.is_dir():
            core_logger.print_to_log_and_console(
                f"Required directory is not a directory: {required_dir}",
                "error",
            )
            raise OSError(f"Required directory is not a directory: {required_dir}")
