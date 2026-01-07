from enum import IntEnum, Enum
import re
from pydantic import (
    BaseModel,
    StrictInt,
    ConfigDict,
    Field,
    field_validator,
)
from core.sanitization import sanitize_attribution


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
    Base schema for server configuration settings.

    Shared fields and validation rules used across all server settings
    schemas. Does not include the id field, allowing flexible inheritance
    for different use cases.

    Attributes:
        units: Measurement units (metric/imperial).
        public_shareable_links: Enable public shareable activity links.
        public_shareable_links_user_info: Show user info on public links.
        login_photo_set: Whether login photo has been configured.
        currency: Currency type (euro/dollar/pound).
        num_records_per_page: Default pagination size.
        signup_enabled: Allow new user registration.
        sso_enabled: Enable SSO/IdP authentication.
        local_login_enabled: Allow username/password login.
        sso_auto_redirect: Auto-redirect to SSO login.
        tileserver_url: Map tile server URL template.
        tileserver_attribution: Map tile attribution HTML.
        map_background_color: Map background hex color.
        password_type: Password policy type.
        password_length_regular_users: Min length for regular users.
        password_length_admin_users: Min length for admin users.
    """

    units: Units = Field(
        Units.METRIC, description="Measurement units (metric/imperial)"
    )
    public_shareable_links: bool = Field(
        ..., description="Enable public shareable activity links"
    )
    public_shareable_links_user_info: bool = Field(
        ..., description="Show user info on public shareable links"
    )
    login_photo_set: bool = Field(
        ..., description="Indicates if login photo has been configured"
    )
    currency: Currency = Field(..., description="Currency type (euro/dollar/pound)")
    num_records_per_page: int = Field(
        ..., description="Default number of records per page for pagination"
    )
    signup_enabled: bool = Field(..., description="Allow new user registration")
    sso_enabled: bool = Field(..., description="Enable SSO/IdP authentication")
    local_login_enabled: bool = Field(..., description="Allow username/password login")
    sso_auto_redirect: bool = Field(..., description="Auto-redirect to SSO login page")
    tileserver_url: str = Field(
        max_length=2048, description="Default map tile server URL template"
    )
    tileserver_attribution: str = Field(
        max_length=1024, description="Default map tile attribution HTML"
    )
    map_background_color: str = Field(
        max_length=7,
        pattern=r"^#[0-9A-Fa-f]{6}$",
        description=("Hex color code for map background (e.g., #dddddd)"),
    )
    password_type: PasswordType = Field(
        PasswordType.STRICT, description="Password policy type"
    )
    password_length_regular_users: int = Field(
        8, description="Minimum password length for regular users"
    )
    password_length_admin_users: int = Field(
        12, description="Minimum password length for admin users"
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
        return sanitize_attribution(value) or ""


class ServerSettings(ServerSettingsBase):
    """
    Internal complete server settings schema with identifier.

    Extends ServerSettingsBase by adding the id field for internal
    operations. Not typically used for API responses.

    Attributes:
        id: Unique identifier (always 1, singleton pattern).
        (plus all fields inherited from ServerSettingsBase)
    """

    id: StrictInt = Field(
        ..., description="Unique identifier for server settings (always 1)"
    )


class ServerSettingsEdit(ServerSettings):
    """
    Edit schema for server settings updates.

    Extends ServerSettings with signup requirement fields.

    Attributes:
        signup_require_admin_approval: Admin approval required.
        signup_require_email_verification: Email verification required.
        (plus all fields inherited from ServerSettings)
    """

    signup_require_admin_approval: bool = Field(
        ...,
        description="Indicates if new user signups require admin approval",
    )
    signup_require_email_verification: bool = Field(
        ...,
        description="Indicates if new user signups require email verification",
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

    template_id: str = Field(
        ...,
        description=("Template identifier (e.g., 'openstreetmap', 'stadia_outdoors')"),
    )
    name: str = Field(..., description="Human-readable name of the tile map template")
    url_template: str = Field(..., description="URL template for fetching map tiles")
    attribution: str = Field(..., description="HTML string for map attribution")
    map_background_color: str = Field(
        max_length=7,
        pattern=r"^#[0-9A-Fa-f]{6}$",
        description=("Hex color code for map background (e.g., #dddddd)"),
    )
    requires_api_key_frontend: bool = Field(
        ...,
        description=(
            "Indicates if an API key is required on the frontend " "to use the tile map"
        ),
    )
    requires_api_key_backend: bool = Field(
        ...,
        description=(
            "Indicates if an API key is required on the backend " "to use the tile map"
        ),
    )

    model_config = ConfigDict(
        from_attributes=True,
        extra="forbid",
    )
