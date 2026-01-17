"""User schema definitions for request and response models."""

from enum import Enum
from datetime import date as datetime_date
from pydantic import (
    BaseModel,
    EmailStr,
    field_validator,
    StrictInt,
    StrictStr,
    StrictBool,
    ConfigDict,
    Field,
)
import server_settings.schema as server_settings_schema


class Gender(Enum):
    """
    User gender enumeration.

    Attributes:
        MALE: Male gender.
        FEMALE: Female gender.
        UNSPECIFIED: Unspecified or undisclosed gender.
    """

    MALE = "male"
    FEMALE = "female"
    UNSPECIFIED = "unspecified"


class Language(Enum):
    """
    Supported application languages.

    Attributes:
        CATALAN: Catalan (ca).
        CHINESE_SIMPLIFIED: Simplified Chinese (cn).
        CHINESE_TRADITIONAL: Traditional Chinese (tw).
        GERMAN: German (de).
        FRENCH: French (fr).
        GALICIAN: Galician (gl).
        ITALIAN: Italian (it).
        DUTCH: Dutch (nl).
        PORTUGUESE: Portuguese (pt).
        SLOVENIAN: Slovenian (sl).
        SWEDISH: Swedish (sv).
        SPANISH: Spanish (es).
        ENGLISH_USA: US English (us).
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


class WeekDay(Enum):
    """
    Days of the week enumeration.

    Attributes:
        SUNDAY: Sunday.
        MONDAY: Monday.
        TUESDAY: Tuesday.
        WEDNESDAY: Wednesday.
        THURSDAY: Thursday.
        FRIDAY: Friday.
        SATURDAY: Saturday.
    """

    SUNDAY = "sunday"
    MONDAY = "monday"
    TUESDAY = "tuesday"
    WEDNESDAY = "wednesday"
    THURSDAY = "thursday"
    FRIDAY = "friday"
    SATURDAY = "saturday"


class UserAccessType(Enum):
    """
    User access level enumeration.

    Attributes:
        REGULAR: Standard user access.
        ADMIN: Administrative access.
    """

    REGULAR = "regular"
    ADMIN = "admin"


class UserBase(BaseModel):
    """
    Base user schema with common fields.

    Attributes:
        name: User's full name (1-250 chars).
        username: Unique username (1-250 chars, alphanumeric
            and dots).
        email: User's email address (max 250 chars).
        city: User's city (max 250 chars).
        birthdate: User's birthdate.
        preferred_language: Preferred language.
        gender: User's gender.
        units: Measurement units preference.
        height: User's height in centimeters (1-300).
        max_heart_rate: Maximum heart rate in bpm (30-250).
        first_day_of_week: First day of the week.
        currency: Currency preference.
    """

    name: StrictStr = Field(
        ...,
        min_length=1,
        max_length=250,
        description="User's full name",
    )
    username: StrictStr = Field(
        ...,
        min_length=1,
        max_length=250,
        pattern=r"^[a-zA-Z0-9.]+$",
        description="Unique username (alphanumeric and dots)",
    )
    email: EmailStr = Field(
        ...,
        max_length=250,
        description="User's email address",
    )
    city: StrictStr | None = Field(
        None,
        max_length=250,
        description="User's city",
    )
    birthdate: datetime_date | None = Field(
        None,
        description="User's birthdate",
    )
    preferred_language: Language = Field(
        Language.ENGLISH_USA,
        description="Preferred language",
    )
    gender: Gender = Field(
        Gender.UNSPECIFIED,
        description="User's gender",
    )
    units: server_settings_schema.Units = Field(
        server_settings_schema.Units.METRIC,
        description="Measurement units",
    )
    height: StrictInt | None = Field(
        None,
        ge=1,
        le=300,
        description="Height in centimeters",
    )
    max_heart_rate: StrictInt | None = Field(
        None,
        ge=30,
        le=250,
        description="Maximum heart rate in bpm",
    )
    first_day_of_week: WeekDay = Field(
        WeekDay.MONDAY,
        description="First day of the week",
    )
    currency: server_settings_schema.Currency = Field(
        server_settings_schema.Currency.EURO,
        description="Currency preference",
    )

    model_config = ConfigDict(use_enum_values=True)

    @field_validator("birthdate", mode="before")
    @classmethod
    def validate_birthdate(cls, value: datetime_date | str | None) -> str | None:
        """
        Convert birthdate to ISO format string.

        Args:
            value: Birthdate as date object, string, or None.

        Returns:
            ISO format date string or None.
        """
        if value is None:
            return None
        if isinstance(value, datetime_date):
            return value.isoformat()
        return value


class User(UserBase):
    """
    Complete user schema with all fields.

    Attributes:
        access_type: User access level.
        photo_path: Path to user's photo.
        active: Whether the user is active.
        mfa_enabled: Whether MFA is enabled.
        mfa_secret: MFA secret (encrypted at rest).
        email_verified: Whether email is verified.
        pending_admin_approval: Whether pending admin approval.
    """

    access_type: UserAccessType = Field(
        ...,
        description="User access level",
    )
    photo_path: StrictStr | None = Field(
        None,
        max_length=250,
        description="Path to user's photo",
    )
    active: StrictBool = Field(
        ...,
        description="Whether the user is active",
    )
    mfa_enabled: StrictBool = Field(
        False,
        description="Whether MFA is enabled",
    )
    mfa_secret: StrictStr | None = Field(
        None,
        max_length=512,
        description="MFA secret (encrypted at rest)",
    )
    email_verified: StrictBool = Field(
        False,
        description="Whether email is verified",
    )
    pending_admin_approval: StrictBool = Field(
        False,
        description="Whether pending admin approval",
    )

    model_config = ConfigDict(
        from_attributes=True,
        extra="forbid",
        validate_assignment=True,
    )


class UserRead(User):
    """
    User schema for read operations.

    Attributes:
        id: User ID.
        external_auth_count: Number of external auth providers.
    """

    id: StrictInt = Field(
        ...,
        ge=1,
        description="User ID",
    )
    external_auth_count: StrictInt = Field(
        0,
        ge=0,
        description="Number of external auth providers linked",
    )


class UserMe(UserRead):
    """
    Extended user schema for current user profile.

    Includes privacy settings and integration status.

    Attributes:
        is_strava_linked: Strava integration status.
        is_garminconnect_linked: Garmin Connect status.
        default_activity_visibility: Default visibility level.
        hide_activity_start_time: Hide start time setting.
        hide_activity_location: Hide location setting.
        hide_activity_map: Hide map setting.
        hide_activity_hr: Hide heart rate setting.
        hide_activity_power: Hide power setting.
        hide_activity_cadence: Hide cadence setting.
        hide_activity_elevation: Hide elevation setting.
        hide_activity_speed: Hide speed setting.
        hide_activity_pace: Hide pace setting.
        hide_activity_laps: Hide laps setting.
        hide_activity_workout_sets_steps: Hide workout
            sets/steps.
        hide_activity_gear: Hide gear setting.
    """

    is_strava_linked: StrictInt | None = None
    is_garminconnect_linked: StrictInt | None = None
    default_activity_visibility: StrictInt | None = None
    hide_activity_start_time: StrictBool | None = None
    hide_activity_location: StrictBool | None = None
    hide_activity_map: StrictBool | None = None
    hide_activity_hr: StrictBool | None = None
    hide_activity_power: StrictBool | None = None
    hide_activity_cadence: StrictBool | None = None
    hide_activity_elevation: StrictBool | None = None
    hide_activity_speed: StrictBool | None = None
    hide_activity_pace: StrictBool | None = None
    hide_activity_laps: StrictBool | None = None
    hide_activity_workout_sets_steps: StrictBool | None = None
    hide_activity_gear: StrictBool | None = None


class UserSignup(UserBase):
    """
    User schema for signup operations.

    Attributes:
        password: User's password (min 8 chars).
    """

    password: StrictStr = Field(
        ...,
        min_length=8,
        max_length=250,
        description="User's password",
    )


class UserCreate(User):
    """
    User schema for admin user creation.

    Attributes:
        password: User's password (min 8 chars).
    """

    password: StrictStr = Field(
        ...,
        min_length=8,
        max_length=250,
        description="User's password",
    )


class UserEditPassword(BaseModel):
    """
    Schema for password update operations.

    Attributes:
        password: New password (min 8 chars).
    """

    password: StrictStr = Field(
        ...,
        min_length=8,
        max_length=250,
        description="New password",
    )

    model_config = ConfigDict(
        extra="forbid",
        validate_assignment=True,
    )


class UserListResponse(BaseModel):
    """
    Response model for paginated user listing.

    Attributes:
        total: Total number of user records.
        num_records: Number of records in this response.
        page_number: Current page number.
        records: List of user records.
    """

    total: StrictInt = Field(
        ...,
        ge=0,
        description="Total number of user records",
    )
    num_records: StrictInt | None = Field(
        None,
        ge=0,
        description="Number of records in this response",
    )
    page_number: StrictInt | None = Field(
        None,
        ge=1,
        description="Current page number",
    )
    records: list[UserRead] = Field(
        ...,
        description="List of user records",
    )

    model_config = ConfigDict(
        from_attributes=True,
        extra="forbid",
        validate_assignment=True,
    )
