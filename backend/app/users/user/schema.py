from enum import Enum, IntEnum
from datetime import date
from pydantic import (
    BaseModel,
    EmailStr,
    field_validator,
    StrictInt,
    ConfigDict,
    Field,
)
import server_settings.schema as server_settings_schema


class Gender(IntEnum):
    """
    An enumeration representing the gender of a user.

    Attributes:
        MALE (int): Represents male gender.
        FEMALE (int): Represents female gender.
        UNSPECIFIED (int): Represents unspecified or undisclosed gender.
    """

    MALE = 1
    FEMALE = 2
    UNSPECIFIED = 3


class Language(Enum):
    """
    An enumeration representing supported languages for the application.

    Members:
        CATALAN: Catalan language code ("ca-ES").
        CHINESE_SIMPLIFIED: Simplified Chinese language code ("cn").
        CHINESE_TRADITIONAL: Traditional Chinese language code ("tw").
        GERMAN: German language code ("de").
        FRENCH: French language code ("fr").
        GALICIAN: Galician language code ("gl").
        ITALIAN: Italian language code ("it").
        DUTCH: Dutch language code ("nl").
        PORTUGUESE: Portuguese language code ("pt").
        SLOVENIAN: Slovenian language code ("sl").
        SWEDISH: Swedish language code ("sv").
        SPANISH: Spanish language code ("es").
        ENGLISH_USA: US English language code ("us").
    """

    CATALAN = "ca"
    CHINESE_SIMPLIFIED = "cn"
    CHINESE_TRADITIONAL = "tw"
    GERMAN = "de"
    FRENCH = "fr"
    GALICIAN = "gl"
    ITALIAN = "it"
    DUTCH = "nl"
    PORTUGUESE = "pt"
    SLOVENIAN = "sl"
    SWEDISH = "sv"
    SPANISH = "es"
    ENGLISH_USA = "us"


class WeekDay(IntEnum):
    """
    An enumeration representing the days of the week.

    Attributes:
        SUNDAY (int): Represents Sunday (0).
        MONDAY (int): Represents Monday (1).
        TUESDAY (int): Represents Tuesday (2).
        WEDNESDAY (int): Represents Wednesday (3).
        THURSDAY (int): Represents Thursday (4).
        FRIDAY (int): Represents Friday (5).
        SATURDAY (int): Represents Saturday (6).
    """

    SUNDAY = 0
    MONDAY = 1
    TUESDAY = 2
    WEDNESDAY = 3
    THURSDAY = 4
    FRIDAY = 5
    SATURDAY = 6


class UserAccessType(IntEnum):
    """
    Enumeration representing different types of user access levels.

    Attributes:
        REGULAR (int): Standard user with regular access permissions.
        ADMIN (int): User with administrative access permissions.
    """

    REGULAR = 1
    ADMIN = 2


class UserBase(BaseModel):
    name: str
    username: str
    email: EmailStr
    city: str | None = None
    birthdate: str | None = None
    preferred_language: Language = Language.ENGLISH_USA
    gender: Gender = Gender.MALE
    units: server_settings_schema.Units = server_settings_schema.Units.METRIC
    height: int | None = None
    max_heart_rate: int | None = None
    first_day_of_week: WeekDay = WeekDay.MONDAY
    currency: server_settings_schema.Currency = server_settings_schema.Currency.EURO

    model_config = ConfigDict(use_enum_values=True)

    @field_validator("birthdate", mode="before")
    @classmethod
    def validate_birthdate(cls, value: date | str | None) -> str | None:
        """
        Validate and convert birthdate field to ISO format string.

        Converts datetime.date objects to ISO format strings (YYYY-MM-DD).
        Handles None values and string values that are already formatted.

        Args:
            value: The birthdate as a date object, string, or None.

        Returns:
            str | None: ISO format date string (YYYY-MM-DD) or None.
        """
        if value is None:
            return None
        if isinstance(value, date):
            return value.isoformat()
        return value


class User(UserBase):
    access_type: UserAccessType
    photo_path: str | None = None
    active: bool
    mfa_enabled: bool = False
    mfa_secret: str | None = None
    email_verified: bool = False
    pending_admin_approval: bool = False

    model_config = ConfigDict(
        from_attributes=True, extra="forbid", validate_assignment=True
    )


class UserRead(User):
    id: StrictInt
    external_auth_count: int = 0


class UserMe(UserRead):
    is_strava_linked: int | None = None
    is_garminconnect_linked: int | None = None
    default_activity_visibility: int | None = None
    hide_activity_start_time: bool | None = None
    hide_activity_location: bool | None = None
    hide_activity_map: bool | None = None
    hide_activity_hr: bool | None = None
    hide_activity_power: bool | None = None
    hide_activity_cadence: bool | None = None
    hide_activity_elevation: bool | None = None
    hide_activity_speed: bool | None = None
    hide_activity_pace: bool | None = None
    hide_activity_laps: bool | None = None
    hide_activity_workout_sets_steps: bool | None = None
    hide_activity_gear: bool | None = None


class UserSignup(UserBase):
    password: str


class UserCreate(User):
    password: str


class UserEditPassword(BaseModel):
    password: str


class UserListResponse(BaseModel):
    """
    Response model for listing user records.

    Attributes:
        total (StrictInt): Total number of user records.
        num_records (StrictInt | None): Number of records in this response.
        page_number (StrictInt | None): Current page number.
        records (list[UserRead]): List of user records.
    """

    total: StrictInt = Field(..., description="Total number of user records")
    num_records: StrictInt | None = Field(
        None, description="Number of records in this response"
    )
    page_number: StrictInt | None = Field(None, description="Current page number")
    records: list[UserRead] = Field(..., description="List of user records")

    model_config = ConfigDict(
        from_attributes=True,
        extra="forbid",
        validate_assignment=True,
    )
