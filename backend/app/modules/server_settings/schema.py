"""Request and response shapes for server settings."""

import re
from enum import Enum

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StrictBool,
    StrictInt,
    StrictStr,
    field_validator,
    model_validator,
)

import core.geocoding as core_geocoding
import core.mail as core_mail
import core.sanitization as core_sanitization


class Units(Enum):
    """An enumeration representing measurement units.

    Attributes:
        METRIC: Metric system (e.g., meters, kilograms).
        IMPERIAL: Imperial system (e.g., miles, pounds).
    """

    METRIC = "metric"
    IMPERIAL = "imperial"


class Currency(Enum):
    """An enumeration representing supported currencies.

    Attributes:
        EURO: Represents the Euro currency.
        DOLLAR: Represents the US Dollar currency.
        POUND: Represents the British Pound currency.
    """

    EURO = "euro"
    DOLLAR = "dollar"
    POUND = "pound"


class PasswordType(Enum):
    """An enumeration representing password policy types.

    Attributes:
        STRICT (str): Strict password policy.
        LENGTH_ONLY (str): Length-only password policy.
    """

    STRICT = "strict"
    LENGTH_ONLY = "length_only"


class ServerSettingsBase(BaseModel):
    """Pydantic model for server settings configuration.

    This model defines all configurable server settings for the Endurain application,
    including units, currency, authentication methods, map configuration, and password policies.

    Attributes:
        units (Units): Unit system for measurements (METRIC or IMPERIAL).
        public_shareable_links (StrictBool): Enable/disable public shareable links.
        public_shareable_links_user_info (StrictBool): Show user info on public shareable links.
        currency (Currency): Currency type (EURO, DOLLAR, or POUND).
        num_records_per_page (StrictInt): Number of records per page in lists (1-100).
        signup_enabled (StrictBool): Allow new user registration.
        sso_enabled (StrictBool): Enable SSO/IdP authentication.
        local_login_enabled (StrictBool): Allow local username/password authentication.
        sso_auto_redirect (StrictBool): Automatically redirect to SSO when only one IdP is configured.
        tileserver_url (StrictStr): URL template for map tile server with coordinate placeholders.
        tileserver_attribution (StrictStr): Attribution string for map tile server.
        map_background_color (StrictStr): Hex color code for map background (#RRGGBB format).
        password_type (PasswordType): Password policy enforcement level (STRICT or LENGTH_ONLY).
        password_length_regular_users (StrictInt): Minimum password length for regular users (8-128).
        password_length_admin_users (StrictInt): Minimum password length for admin users (8-128).

    Validators:
        - validate_tileserver_url: Ensures tile server URL is secure, uses proper protocol, contains required placeholders, and blocks dangerous patterns.
        - validate_attribution: Sanitizes attribution string to prevent XSS attacks.

    Model Config:
        - Validates on assignment.
        - Forbids extra fields.
        - Uses enum values in serialization.
        - Supports ORM attribute mapping.
    """

    units: Units = Field(..., description="Units (metric, imperial)")
    public_shareable_links: StrictBool = Field(..., description="Allow public shareable links (true - yes, false - no)")
    public_shareable_links_user_info: StrictBool = Field(
        ...,
        description="Allow show user info on public shareable links (true - yes, false - no)",
    )
    currency: Currency = Field(..., description="Currency (euro, dollar, pound)")
    num_records_per_page: StrictInt = Field(
        ...,
        ge=1,
        le=100,
        description="Number of records per page in lists",
    )
    signup_enabled: StrictBool = Field(..., description="Allow user sign-up registration (true - yes, false - no)")
    sso_enabled: StrictBool = Field(
        ...,
        description="Enable SSO/IdP login (true - yes, false - no)",
    )
    local_login_enabled: StrictBool = Field(
        ..., description="Allow local username/password login (true - yes, false - no)"
    )
    sso_auto_redirect: StrictBool = Field(
        ..., description="Auto-redirect to SSO if only one IdP (true - yes, false - no)"
    )
    tileserver_url: StrictStr = Field(
        max_length=2048,
        min_length=1,
        description="URL template for the map tileserver",
    )
    tileserver_attribution: StrictStr = Field(
        max_length=1024,
        min_length=1,
        description="Attribution string for the map tileserver",
    )
    map_background_color: StrictStr = Field(
        max_length=7,
        pattern=r"^#[0-9A-Fa-f]{6}$",
        description=("Background color for the map (hex format)"),
    )
    tileserver_regenerate_thumbnails_on_change: StrictBool = Field(
        ...,
        description=("Delete and regenerate all activity thumbnails when tile server settings change"),
    )
    password_type: PasswordType = Field(..., description="Password type policy (strict, length_only)")
    password_length_regular_users: StrictInt = Field(
        ..., ge=8, le=128, description="Minimum password length for regular users"
    )
    password_length_admin_users: StrictInt = Field(
        ..., ge=8, le=128, description="Minimum password length for admin users"
    )

    model_config = ConfigDict(
        from_attributes=True,
        extra="forbid",
        validate_assignment=True,
        use_enum_values=True,
    )

    @field_validator("tileserver_url")
    @classmethod
    def validate_tileserver_url(cls, value: str) -> str:
        """Validate tile server URL for security and correctness.

        Args:
            value: Tile server URL template.

        Returns:
            Validated URL.

        Raises:
            ValueError: If URL is invalid or insecure.
        """
        if not value:
            return value

        # Must use http or https protocol
        if not re.match(r"^https?://", value, re.IGNORECASE):
            raise ValueError("Tile server URL must use http:// or https://")

        # Enforce HTTPS except for localhost
        if value.lower().startswith("http://") and not re.match(
            r"^http://(localhost|127\.0\.0\.1)(:|/)",
            value,
            re.IGNORECASE,
        ):
            raise ValueError("Tile server URL must use https:// (http:// only allowed for localhost)")

        # Must contain required tile coordinate placeholders
        required = ["{z}", "{x}", "{y}"]
        missing = [p for p in required if p not in value]
        if missing:
            missing_str = ", ".join(missing)
            raise ValueError(f"Tile server URL must contain placeholders: {missing_str}")

        # Block dangerous patterns
        dangerous = [
            r"javascript:",
            r"data:",
            r"vbscript:",
            r"file:",
            r"<script",
            r"onerror",
            r"onclick",
        ]

        for pattern in dangerous:
            if re.search(pattern, value, re.IGNORECASE):
                msg = f"Tile server URL contains disallowed: {pattern}"
                raise ValueError(msg)

        return value

    @field_validator("tileserver_attribution")
    @classmethod
    def validate_attribution(cls, value: str) -> str:
        """Sanitize tileserver attribution to prevent XSS.

        Args:
            value: Raw attribution string.

        Returns:
            Sanitized string with only safe HTML.
        """
        return core_sanitization.sanitize_attribution(value) or ""


#: Bare ``host[:port]`` authority: a hostname, IPv4 address or bracketed IPv6 literal, no scheme or path.
_GEOCODING_HOST_PATTERN = re.compile(r"^([A-Za-z0-9]([A-Za-z0-9.-]*[A-Za-z0-9])?|\[[0-9A-Fa-f:.]+\])(:[0-9]{1,5})?$")


class ServerSettingsGeocoding(BaseModel):
    """The reverse-geocoding fields, kept off the public settings model.

    A separate mixin rather than part of :class:`ServerSettingsBase`, which the public
    settings inherit: the geocoding host of a self-hosted instance is not for anonymous visitors.

    Attributes:
        geocoding_service: The reverse-geocoding service.
        geocoding_host: Host (and optional port) of the service; empty for the service's default host.
        geocoding_use_https: Address the host over HTTPS.
        geocoding_rate_limit: Maximum requests per second (0 disables throttling).
    """

    geocoding_service: core_geocoding.GeocodingService = Field(
        ..., description="Reverse-geocoding service (nominatim, photon, geocode)"
    )
    geocoding_host: StrictStr | None = Field(
        ...,
        max_length=253,
        description="Host of the geocoding service, e.g. nominatim.example.org:8080 (empty - the service's default)",
    )
    geocoding_use_https: StrictBool = Field(
        ..., description="Address the geocoding host over HTTPS (true - yes, false - no)"
    )
    geocoding_rate_limit: float = Field(
        ..., ge=0, le=100, description="Maximum geocoding requests per second (0 disables throttling)"
    )

    @field_validator("geocoding_host", mode="after")
    @classmethod
    def validate_geocoding_host(cls, value: str | None) -> str | None:
        """Normalise the geocoding host and refuse anything but ``host[:port]``.

        Args:
            value: The submitted host.

        Returns:
            The lower-cased host, or None when blank.

        Raises:
            ValueError: If the value carries a scheme, path or other characters.
        """
        value = (value or "").strip().lower()
        if not value:
            return None
        if not _GEOCODING_HOST_PATTERN.fullmatch(value):
            raise ValueError("Geocoding host must be a hostname or IP address with an optional port")
        return value


class ServerSettingsSessionPolicy(BaseModel):
    """The session and token policy fields, kept off the public settings model.

    Attributes:
        session_idle_timeout_enabled: Enforce the idle and absolute session timeouts.
        session_idle_timeout_hours: Hours of inactivity that end a session (1-8760).
        session_absolute_timeout_hours: Hours after which a session ends (1-8760, not below the idle timeout).
        access_token_expire_minutes: Access token lifetime in minutes (1-1440).
        refresh_token_expire_days: Refresh token lifetime in days (1-365).
    """

    session_idle_timeout_enabled: StrictBool = Field(
        ..., description="Enforce session idle and absolute timeouts (true - yes, false - no)"
    )
    session_idle_timeout_hours: StrictInt = Field(
        ..., ge=1, le=8760, description="Hours of inactivity after which a session ends"
    )
    session_absolute_timeout_hours: StrictInt = Field(
        ..., ge=1, le=8760, description="Hours after which a session ends whatever its activity"
    )
    access_token_expire_minutes: StrictInt = Field(..., ge=1, le=1440, description="Access token lifetime in minutes")
    refresh_token_expire_days: StrictInt = Field(..., ge=1, le=365, description="Refresh token lifetime in days")

    @model_validator(mode="after")
    def validate_absolute_timeout(self) -> "ServerSettingsSessionPolicy":
        """Refuse an absolute timeout shorter than the idle timeout.

        Returns:
            The validated model.

        Raises:
            ValueError: If the absolute timeout is below the idle timeout.
        """
        if self.session_absolute_timeout_hours < self.session_idle_timeout_hours:
            raise ValueError("The absolute session timeout cannot be shorter than the idle timeout")
        return self


class ServerSettingsRetention(BaseModel):
    """The data retention fields, kept off the public settings model.

    Attributes:
        read_notification_retention_days: Days after which read notifications are purged (0 disables pruning).
    """

    read_notification_retention_days: StrictInt = Field(
        ..., ge=0, le=3650, description="Days after which read notifications are purged (0 - never)"
    )


class ServerSettingsEdit(
    ServerSettingsBase, ServerSettingsGeocoding, ServerSettingsSessionPolicy, ServerSettingsRetention
):
    """Request body for editing the server settings.

    A full replacement: every setting except the tile API key is required. The row
    id and the login-photo flag are not here: the id is fixed (singleton) and the
    flag is set only by the login-photo upload and delete routes, so a stale form
    can never reset it.

    Attributes:
        tileserver_api_key: Plain-text API key for the tile server; stored encrypted
            and never returned. Omit it to keep the stored key; send null or an
            empty string to remove it.
        signup_require_admin_approval: Require admin approval for new sign-ups
            (true - yes, false - no).
        signup_require_email_verification: Require email verification for new
            sign-ups (true - yes, false - no).
        geocoding_api_key: Plain-text API key for the geocoding service; same
            write-only semantics as ``tileserver_api_key``.
    """

    # Capped so the Fernet token (about 1.37x the plain length) fits the 512-char column.
    tileserver_api_key: StrictStr | None = Field(
        default=None,
        max_length=256,
        description="API key for the tile server (write-only); omit to keep, null or empty to remove",
    )
    geocoding_api_key: StrictStr | None = Field(
        default=None,
        max_length=256,
        description="API key for the geocoding service (write-only); omit to keep, null or empty to remove",
    )
    signup_require_admin_approval: StrictBool = Field(
        ...,
        description="Require admin approval for new sign-ups (true - yes, false - no)",
    )
    signup_require_email_verification: StrictBool = Field(
        ...,
        description="Require email verification for new sign-ups (true - yes, false - no)",
    )


class ServerSettingsRead(ServerSettingsEdit):
    """The settings row as stored, for in-process use only.

    Never a response model: the tile API key is the stored (encrypted) value.
    Clients get :class:`ServerSettingsAdminRead` or :class:`ServerSettingsReadPublic`.

    Attributes:
        id: Unique identifier (always 1, singleton pattern).
        login_photo_set: Whether a custom login photo is configured.
        version: Optimistic-concurrency counter, also sent as the ``ETag``.
    """

    # Wider than the edit cap: the stored value is the Fernet token, which this model also reads.
    tileserver_api_key: StrictStr | None = Field(
        default=None,
        max_length=512,
        description="API key for the tile server",
    )
    geocoding_api_key: StrictStr | None = Field(
        default=None,
        max_length=512,
        description="API key for the geocoding service",
    )
    id: StrictInt = Field(..., description="Unique identifier for server settings (always 1)")
    login_photo_set: StrictBool = Field(..., description="Is login photo set (true - yes, false - no)")
    version: StrictInt = Field(default=1, ge=1, description="Optimistic-concurrency counter")


class ServerSettingsAdminRead(
    ServerSettingsBase, ServerSettingsGeocoding, ServerSettingsSessionPolicy, ServerSettingsRetention
):
    """Complete server settings response for admins; API keys are never returned.

    Attributes:
        id: Unique identifier (always 1, singleton pattern).
        login_photo_set: Whether a custom login photo is configured.
        version: Optimistic-concurrency counter, also sent as the ``ETag``.
        tileserver_api_key_set: Whether a tile API key is stored.
        geocoding_api_key_set: Whether a geocoding API key is stored.
        env_managed: Field name to the environment variable that sets it; those
            fields cannot be edited while the variable is set.
        signup_require_admin_approval: Require admin approval for new sign-ups.
        signup_require_email_verification: Require email verification for new sign-ups.
    """

    id: StrictInt = Field(..., description="Unique identifier for server settings (always 1)")
    login_photo_set: StrictBool = Field(..., description="Is login photo set (true - yes, false - no)")
    version: StrictInt = Field(..., ge=1, description="Optimistic-concurrency counter")
    tileserver_api_key_set: StrictBool = Field(
        ..., description="Is a tile server API key stored (true - yes, false - no)"
    )
    geocoding_api_key_set: StrictBool = Field(..., description="Is a geocoding API key stored (true - yes, false - no)")
    env_managed: dict[str, str] = Field(
        ..., description="Field name to the environment variable that sets it (not editable while set)"
    )
    signup_require_admin_approval: StrictBool = Field(
        ...,
        description="Require admin approval for new sign-ups (true - yes, false - no)",
    )
    signup_require_email_verification: StrictBool = Field(
        ...,
        description="Require email verification for new sign-ups (true - yes, false - no)",
    )


class ServerSettingsReadPublic(ServerSettingsBase):
    """Public-facing schema for unauthenticated server settings access.

    Provides only public-safe server settings, excluding sensitive
    configuration like signup requirements. Used for the public API
    endpoint that doesn't require authentication.

    Inherits all safe fields from ServerSettingsBase but explicitly
    excludes admin-level configuration fields.

    Attributes:
        login_photo_set: Whether a custom login photo is configured.
        allowed_redirect_schemes: Custom URI schemes (ALLOWED_REDIRECT_SCHEMES) that
            SSO redirects may target, so the frontend validates the same allow-list
            as the backend.
    """

    login_photo_set: StrictBool = Field(..., description="Is login photo set (true - yes, false - no)")
    allowed_redirect_schemes: list[str] = Field(
        ...,
        description="Custom URI schemes SSO redirects may target",
    )


class TileMapsTemplate(BaseModel):
    """Schema representing available tile map templates.

    Attributes:
        name: Human-readable name of the tile map template.
        url_template: URL template for fetching map tiles.
        attribution: HTML string for map attribution.
        requires_api_key_frontend: Indicates if an API key is required on the
            frontend to use the tile map.
        requires_api_key_backend: Indicates if an API key is required on the
            backend to use the tile map.
    """

    template_id: StrictStr = Field(
        ...,
        min_length=1,
        description=("Template identifier (e.g., 'openstreetmap', 'stadia_outdoors')"),
    )
    name: StrictStr = Field(..., min_length=1, description="Human-readable name of the tile map template")
    url_template: StrictStr = Field(..., min_length=1, description="URL template for fetching map tiles")
    attribution: StrictStr = Field(..., min_length=1, description="HTML string for map attribution")
    map_background_color: StrictStr = Field(
        max_length=7,
        min_length=7,
        pattern=r"^#[0-9A-Fa-f]{6}$",
        description=("Hex color code for map background (e.g., #dddddd)"),
    )
    requires_api_key_frontend: StrictBool = Field(
        ...,
        description=("Indicates if an API key is required on the frontend to use the tile map"),
    )
    requires_api_key_backend: StrictBool = Field(
        ...,
        description=("Indicates if an API key is required on the backend to use the tile map"),
    )

    model_config = ConfigDict(
        from_attributes=True,
        extra="forbid",
    )


class MailSettingsEdit(BaseModel):
    """Request body for editing the mail server settings.

    A full replacement except for the password.

    Attributes:
        host: Mail server hostname; empty or null disables mail.
        port: Mail server port.
        security: Connection security.
        username: Authentication username.
        from_address: Sender address; the username is used when empty.
        password: Plain-text password; stored encrypted and never returned. Omit it
            to keep the stored password; send null or an empty string to remove it.
    """

    host: StrictStr | None = Field(..., max_length=253, description="Mail server hostname (empty - mail disabled)")
    port: StrictInt = Field(..., ge=1, le=65535, description="Mail server port")
    security: core_mail.MailSecurity = Field(..., description="Connection security (starttls, ssl, none)")
    username: StrictStr | None = Field(..., max_length=320, description="Mail server authentication username")
    from_address: StrictStr | None = Field(
        ..., max_length=320, description="Sender address (empty - the username is used)"
    )
    # Capped so the Fernet token (about 1.37x the plain length) fits the 512-char column.
    password: StrictStr | None = Field(
        default=None,
        max_length=256,
        description="Mail server password (write-only); omit to keep, null or empty to remove",
    )

    model_config = ConfigDict(extra="forbid", use_enum_values=True)

    @field_validator("host", "username", "from_address", mode="after")
    @classmethod
    def _empty_to_none(cls, value: str | None) -> str | None:
        """Treat a blank string as unset.

        Args:
            value: The submitted value.

        Returns:
            The stripped value, or None when it is blank.
        """
        return (value.strip() or None) if value is not None else None


class MailSettingsRead(MailSettingsEdit):
    """The mail settings row as stored, for in-process use only.

    Never a response model: the password is the stored (encrypted) value.

    Attributes:
        id: Unique identifier (always 1, singleton pattern).
        version: Optimistic-concurrency counter, also sent as the ``ETag``.
    """

    model_config = ConfigDict(from_attributes=True, extra="forbid", use_enum_values=True)

    # Wider than the edit cap: the stored value is the Fernet token, which this model also reads.
    password: StrictStr | None = Field(default=None, max_length=512, description="Mail server password")
    id: StrictInt = Field(..., description="Unique identifier for mail settings (always 1)")
    version: StrictInt = Field(default=1, ge=1, description="Optimistic-concurrency counter")


class MailSettingsAdminRead(BaseModel):
    """Mail server settings response for admins; the password is never returned.

    Attributes:
        id: Unique identifier (always 1, singleton pattern).
        version: Optimistic-concurrency counter, also sent as the ``ETag``.
        host: Mail server hostname, or null when mail is disabled.
        port: Mail server port.
        security: Connection security.
        username: Authentication username.
        from_address: Sender address, or null when the username is used.
        password_set: Whether a password is stored.
        env_managed: Field name to the environment variable that sets it; those
            fields cannot be edited while the variable is set.
    """

    id: StrictInt
    version: StrictInt = Field(..., ge=1, description="Optimistic-concurrency counter")
    host: StrictStr | None
    port: StrictInt
    security: core_mail.MailSecurity
    username: StrictStr | None
    from_address: StrictStr | None
    password_set: StrictBool = Field(..., description="Is a mail server password stored (true - yes, false - no)")
    env_managed: dict[str, str] = Field(
        ..., description="Field name to the environment variable that sets it (not editable while set)"
    )

    model_config = ConfigDict(use_enum_values=True)


class EmailStatus(BaseModel):
    """Whether outgoing email is usable, and why not when it is not.

    Attributes:
        configured: True when the mail settings are valid and email can be sent.
        problems: Reasons email is disabled. Names settings, never their values.
    """

    configured: bool
    problems: list[str]
