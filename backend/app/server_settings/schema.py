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
    Represents the configuration settings for the server.

    Attributes:
        id (StrictInt): Unique identifier for the server settings.
        units (Units): Measurement units used by the server.
        public_shareable_links (bool): Indicates if public shareable links are enabled.
        public_shareable_links_user_info (bool): Indicates if user info is included in public shareable links.
        login_photo_set (bool): Indicates if a login photo is set.
        currency (Currency): Currency used by the server.
        num_records_per_page (int): Number of records displayed per page.
        signup_enabled (bool): Indicates if user signup is enabled.
        signup_require_admin_approval (bool): Indicates if admin approval is required for signup.
        signup_require_email_verification (bool): Indicates if email verification is required for signup.

    Config:
        from_attributes (bool): Allows model creation from attribute dictionaries.
        extra (str): Forbids extra fields not defined in the model.
        validate_assignment (bool): Enables validation on assignment.
    """

    id: StrictInt
    units: Units
    public_shareable_links: bool
    public_shareable_links_user_info: bool
    login_photo_set: bool
    currency: Currency
    num_records_per_page: int
    signup_enabled: bool
    signup_require_admin_approval: bool
    signup_require_email_verification: bool

    model_config = ConfigDict(
        from_attributes=True, extra="forbid", validate_assignment=True
    )
