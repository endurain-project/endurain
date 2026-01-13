from enum import IntEnum, Enum
import re
from pydantic import (
    BaseModel,
    StrictInt,
    StrictBool,
    StrictStr,
    ConfigDict,
    Field,
    field_validator,
)

import core.sanitization as core_sanitization

# Default allowed tile domains for map tiles
DEFAULT_ALLOWED_TILE_DOMAINS: list[str] = [
    "https://*.openstreetmap.org",  # OpenStreetMap
    "https://*.stadiamaps.com",  # Stadia Maps
]


class Units(IntEnum):
    """
    An enumeration representing measurement units.

    Attributes:
        METRIC (int): Metric system (e.g., meters, kilograms).
        IMPERIAL (int): Imperial system (e.g., miles, pounds).
    """

    METRIC = 1
    IMPERIAL = 2


class Currency(IntEnum):
    """
    An enumeration representing supported currencies.

    Attributes:
        EURO (int): Represents the Euro currency.
        DOLLAR (int): Represents the US Dollar currency.
        POUND (int): Represents the British Pound currency.
    """

    EURO = 1
    DOLLAR = 2
    POUND = 3


class PasswordType(Enum):
    """
    An enumeration representing password policy types.

    Attributes:
        STRICT (str): Strict password policy.
        LENGTH_ONLY (str): Length-only password policy.
    """

    STRICT = "strict"
    LENGTH_ONLY = "length_only"


class ServerSettingsBase(BaseModel):
    """
    Pydantic model for server settings configuration.

    This model defines all configurable server settings for the Endurain application,
    including units, currency, authentication methods, map configuration, and password policies.

    Attributes:
        units (Units): Unit system for measurements (METRIC or IMPERIAL).
        public_shareable_links (StrictBool): Enable/disable public shareable links.
        public_shareable_links_user_info (StrictBool): Show user info on public shareable links.
        login_photo_set (StrictBool): Whether login photo is configured.
        currency (Currency): Currency type (EURO, DOLLAR, or POUND).
        num_records_per_page (StrictInt): Number of records per page in lists (1-100, default: 25).
        signup_enabled (StrictBool): Allow new user registration.
        sso_enabled (StrictBool): Enable SSO/IdP authentication.
        local_login_enabled (StrictBool): Allow local username/password authentication.
        sso_auto_redirect (StrictBool): Automatically redirect to SSO when only one IdP is configured.
        tileserver_url (StrictStr): URL template for map tile server with coordinate placeholders.
        tileserver_attribution (StrictStr): Attribution string for map tile server.
        map_background_color (StrictStr): Hex color code for map background (#RRGGBB format).
        password_type (PasswordType): Password policy enforcement level (STRICT or LENGTH_ONLY).
        password_length_regular_users (StrictInt): Minimum password length for regular users (8-128, default: 8).
        password_length_admin_users (StrictInt): Minimum password length for admin users (8-128, default: 12).

    Validators:
        - validate_tileserver_url: Ensures tile server URL is secure, uses proper protocol, contains required placeholders, and blocks dangerous patterns.
        - validate_attribution: Sanitizes attribution string to prevent XSS attacks.

    Model Config:
        - Validates on assignment.
        - Forbids extra fields.
        - Uses enum values in serialization.
        - Supports ORM attribute mapping.
    """

    units: Units = Field(
        Units.METRIC, description="Units (one digit)(1 - metric, 2 - imperial)"
    )
    public_shareable_links: StrictBool = Field(
        ..., description="Allow public shareable links (true - yes, false - no)"
    )
    public_shareable_links_user_info: StrictBool = Field(
        ...,
        description="Allow show user info on public shareable links (true - yes, false - no)",
    )
    login_photo_set: StrictBool = Field(
        ..., description="Is login photo set (true - yes, false - no)"
    )
    currency: Currency = Field(
        ..., description="Currency (one digit)(1 - euro, 2 - dollar, 3 - pound)"
    )
    num_records_per_page: StrictInt = Field(
        25,
        ge=1,
        le=100,
        description="Number of records per page in lists",
    )
    signup_enabled: StrictBool = Field(
        ..., description="Allow user sign-up registration (true - yes, false - no)"
    )
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
    password_type: PasswordType = Field(
        PasswordType.STRICT, description="Password type policy (strict, length_only)"
    )
    password_length_regular_users: StrictInt = Field(
        8, ge=8, le=128, description="Minimum password length for regular users"
    )
    password_length_admin_users: StrictInt = Field(
        12, ge=8, le=128, description="Minimum password length for admin users"
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
        """
        Validate tile server URL for security and correctness.

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
        if value.lower().startswith("http://"):
            if not re.match(
                r"^http://(localhost|127\.0\.0\.1)(:|/)",
                value,
                re.IGNORECASE,
            ):
                raise ValueError(
                    "Tile server URL must use https:// "
                    "(http:// only allowed for localhost)"
                )

        # Must contain required tile coordinate placeholders
        required = ["{z}", "{x}", "{y}"]
        missing = [p for p in required if p not in value.lower()]
        if missing:
            missing_str = ", ".join(missing)
            raise ValueError(
                f"Tile server URL must contain placeholders: {missing_str}"
            )

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
        """
        Sanitize tileserver attribution to prevent XSS.

        Args:
            value: Raw attribution string.

        Returns:
            Sanitized string with only safe HTML.
        """
        return core_sanitization.sanitize_attribution(value) or ""


class ServerSettings(ServerSettingsBase):
    """
    Internal complete server settings schema with identifier.

    Extends ServerSettingsBase by adding the id field for internal
    operations. Not typically used for API responses.

    Attributes:
        id: Unique identifier (always 1, singleton pattern).
        tileserver_api_key: API key encrypted for the tile server.
        (plus all fields inherited from ServerSettingsBase)
    """

    id: StrictInt = Field(
        ..., description="Unique identifier for server settings (always 1)"
    )
    tileserver_api_key: StrictStr | None = Field(
        default=None,
        max_length=512,
        description="API key encrypted for the tile server",
    )


class ServerSettingsEdit(ServerSettings):
    """
    Edit schema for server settings updates.

    Extends ServerSettings with signup requirement fields.

    Attributes:
        signup_require_admin_approval: Require admin approval for new sign-ups
            (true - yes, false - no).
        signup_require_email_verification: Require email verification for new
            sign-ups (true - yes, false - no).
        (plus all fields inherited from ServerSettings)
    """

    signup_require_admin_approval: StrictBool = Field(
        ...,
        description="Require admin approval for new sign-ups (true - yes, false - no)",
    )
    signup_require_email_verification: StrictBool = Field(
        ...,
        description="Require email verification for new sign-ups (true - yes, false - no)",
    )


class ServerSettingsRead(ServerSettingsEdit):
    """
    Complete server settings response schema for API responses.

    Read-only view of all server settings including administrative
    signup configuration. Used for authenticated endpoints returning
    complete server configuration.
    """


class ServerSettingsReadPublic(ServerSettingsBase):
    """
    Public-facing schema for unauthenticated server settings access.

    Provides only public-safe server settings, excluding sensitive
    configuration like signup requirements. Used for the public API
    endpoint that doesn't require authentication.

    Inherits all safe fields from ServerSettingsBase but explicitly
    excludes admin-level configuration fields.
    """


class TileMapsTemplate(BaseModel):
    """
    Schema representing available tile map templates.

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
    name: StrictStr = Field(
        ..., min_length=1, description="Human-readable name of the tile map template"
    )
    url_template: StrictStr = Field(
        ..., min_length=1, description="URL template for fetching map tiles"
    )
    attribution: StrictStr = Field(
        ..., min_length=1, description="HTML string for map attribution"
    )
    map_background_color: StrictStr = Field(
        max_length=7,
        min_length=7,
        pattern=r"^#[0-9A-Fa-f]{6}$",
        description=("Hex color code for map background (e.g., #dddddd)"),
    )
    requires_api_key_frontend: StrictBool = Field(
        ...,
        description=(
            "Indicates if an API key is required on the frontend " "to use the tile map"
        ),
    )
    requires_api_key_backend: StrictBool = Field(
        ...,
        description=(
            "Indicates if an API key is required on the backend " "to use the tile map"
        ),
    )

    model_config = ConfigDict(
        from_attributes=True,
        extra="forbid",
    )
