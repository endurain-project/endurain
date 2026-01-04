from enum import IntEnum
import html
import re
from pydantic import (
    BaseModel,
    StrictInt,
    ConfigDict,
    Field,
    field_validator,
    ValidationError,
)


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


class ServerSettings(BaseModel):
    """
    Represents the configuration settings for a server.

    Attributes:
        id (StrictInt): Unique identifier for the server settings.
        units (Units): Measurement units used by the server.
        public_shareable_links (bool): Indicates if public shareable links are enabled.
        public_shareable_links_user_info (bool): Indicates if user information is included in public shareable links.
        login_photo_set (bool): Specifies if a login photo has been set.
        currency (Currency): Currency used by the server.
        num_records_per_page (int): Number of records displayed per page.
        signup_enabled (bool): Indicates if user signup is enabled.
        sso_enabled (bool): Indicates if SSO/IdP login is enabled.
        local_login_enabled (bool): Indicates if local username/password login is allowed.
        sso_auto_redirect (bool): Auto-redirect to SSO if only one IdP is configured.
        tileserver_url (str): URL template for the map tileserver.
        tileserver_attribution (str): Attribution string for the map tileserver.
        map_background_color (str): Background color for the map.
    """

    id: StrictInt
    units: Units
    public_shareable_links: bool
    public_shareable_links_user_info: bool
    login_photo_set: bool
    currency: Currency
    num_records_per_page: int
    signup_enabled: bool
    sso_enabled: bool
    local_login_enabled: bool
    sso_auto_redirect: bool
    tileserver_url: str = Field(max_length=2048)
    tileserver_attribution: str = Field(max_length=1024)
    map_background_color: str = Field(
        max_length=7,
        pattern=r"^#[0-9A-Fa-f]{6}$",
        description=("Hex color code for map background (e.g., #dddddd)"),
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
            raise ValueError(
                "Tile server URL must contain placeholders: " f"{', '.join(missing)}"
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
                raise ValueError(f"Tile server URL contains disallowed: {pattern}")

        return value

    @field_validator("tileserver_attribution")
    @classmethod
    def sanitize_attribution(cls, value: str) -> str:
        """
        Sanitize tileserver attribution to prevent XSS.

        Args:
            value: Raw attribution string.

        Returns:
            Sanitized string with only safe HTML.
        """
        if not value:
            return value

        # Pattern for anchor tags with http/https URLs
        safe_link_pattern = re.compile(
            r"<a\s+([^>]+)>(.*?)</a>", re.IGNORECASE | re.DOTALL
        )

        safe_links = []
        placeholder_template = "___SAFE_LINK_{}___"

        def extract_link(match):
            attrs_str = match.group(1)
            text = match.group(2)

            # Extract href attribute
            href_match = re.search(
                r'href=(["\'])?(https?://[^\s"\'>]+)\1?',
                attrs_str,
                re.IGNORECASE,
            )
            if not href_match:
                return html.escape(match.group(0))

            url = href_match.group(2)

            # Block dangerous URL protocols
            if url.lower().startswith(("javascript:", "data:", "vbscript:")):
                return html.escape(match.group(0))

            # Extract safe attributes (title, target, rel)
            safe_attrs = ['href="{}"'.format(url)]
            for attr in ["title", "target", "rel"]:
                attr_match = re.search(
                    rf'{attr}=(["\'])([^\1]*?)\1',
                    attrs_str,
                    re.IGNORECASE,
                )
                if attr_match:
                    attr_value = html.escape(attr_match.group(2))
                    safe_attrs.append('{}="{}"'.format(attr, attr_value))

            link = "<a {}>{}</a>".format(" ".join(safe_attrs), text)
            safe_links.append(link)
            return placeholder_template.format(len(safe_links) - 1)

        # Replace safe links with placeholders
        temp = safe_link_pattern.sub(extract_link, value)

        # Preserve HTML entities while escaping dangerous content
        html_entity_pattern = re.compile(r"&[a-zA-Z]+;|&#\d+;")
        entities = []
        entity_placeholder = "___ENTITY_{}___"

        def extract_entity(match):
            entities.append(match.group(0))
            return entity_placeholder.format(len(entities) - 1)

        # Extract HTML entities
        temp = html_entity_pattern.sub(extract_entity, temp)

        # Escape remaining HTML
        sanitized = html.escape(temp)

        # Restore HTML entities
        for idx, entity in enumerate(entities):
            sanitized = sanitized.replace(entity_placeholder.format(idx), entity)

        # Restore safe links
        for idx, link in enumerate(safe_links):
            sanitized = sanitized.replace(placeholder_template.format(idx), link)

        return sanitized


class ServerSettingsEdit(ServerSettings):
    """
    Extends ServerSettings with additional fields for user signup configuration.

    Attributes:
        signup_require_admin_approval (bool): Indicates if new user signups require admin approval.
        signup_require_email_verification (bool): Indicates if new user signups require email verification.
    """

    signup_require_admin_approval: bool
    signup_require_email_verification: bool


class ServerSettingsRead(ServerSettingsEdit):
    """
    Represents a read-only view of server settings, inheriting all fields and validation from ServerSettingsEdit.
    This class is typically used for serializing server settings data for API responses.
    """


class ServerSettingsReadPublic(ServerSettings):
    """
    A public-facing schema for reading server settings.

    This class inherits all fields and behaviors from `ServerSettings` and is intended
    for use cases where only public server settings should be exposed.
    """
