from enum import Enum, IntEnum
from pydantic import BaseModel, EmailStr, field_validator, StrictInt, ConfigDict
import re
import server_settings.schema as server_settings_schema


class Gender(IntEnum):
    MALE = 1
    FEMALE = 2
    UNSPECIFIED = 3


class Language(Enum):
    CATALAN = "ca"
    DUTCH = "nl"
    GERMAN = "de"
    FRENCH = "fr"
    SPANISH = "es"
    PORTUGUESE = "pt"
    ENGLISH_USA = "us"


class WeekDay(IntEnum):
    SUNDAY = 0
    MONDAY = 1
    TUESDAY = 2
    WEDNESDAY = 3
    THURSDAY = 4
    FRIDAY = 5
    SATURDAY = 6


class UserAccessType(IntEnum):
    REGULAR = 1
    ADMIN = 2


PASSWORD_REGEX = r"^(?=.*[A-Z])(?=.*\d)(?=.*[ !\"#$%&'()*+,\-./:;<=>?@[\\\]^_`{|}~])[A-Za-z\d !\"#$%&'()*+,\-./:;<=>?@[\\\]^_`{|}~]{8,}$"


def validate_password(value: str) -> str:
    if not re.match(PASSWORD_REGEX, value):
        raise ValueError(
            "Password must be at least 8 characters long, include an uppercase letter, a number, and a special character."
        )
    return value


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
    first_day_of_week: WeekDay = WeekDay.MONDAY
    currency: server_settings_schema.Currency = server_settings_schema.Currency.EURO


class User(UserBase):
    id: StrictInt
    access_type: UserAccessType
    photo_path: str | None = None
    active: bool
    mfa_enabled: bool = False
    mfa_secret: str | None = None
    email_verified: bool = False
    email_verification_token: str | None = None
    pending_admin_approval: bool = False

    model_config = ConfigDict(
        from_attributes=True, extra="forbid", validate_assignment=True
    )


class UserMe(User):
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

    @field_validator("password")
    def validate_password_field(cls, value):
        return validate_password(value)


class UserCreate(User):
    id: StrictInt
    password: str

    @field_validator("password")
    def validate_password_field(cls, value):
        return validate_password(value)


class UserEditPassword(BaseModel):
    password: str

    @field_validator("password")
    def validate_password_field(cls, value):
        return validate_password(value)
