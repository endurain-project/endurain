from enum import IntEnum
from pydantic import BaseModel, StrictInt, ConfigDict


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
    tileserver_url: str
    tileserver_attribution: str
    map_background_color: str

    model_config = ConfigDict(
        from_attributes=True,
        extra="forbid",
        validate_assignment=True,
        use_enum_values=True,
    )


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
