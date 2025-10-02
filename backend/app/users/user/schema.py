from pydantic import BaseModel, EmailStr, field_validator
import re

PASSWORD_REGEX = r"^(?=.*[A-Z])(?=.*\d)(?=.*[ !\"#$%&'()*+,\-./:;<=>?@[\\\]^_`{|}~])[A-Za-z\d !\"#$%&'()*+,\-./:;<=>?@[\\\]^_`{|}~]{8,}$"


def validate_password(value: str) -> str:
    if not re.match(PASSWORD_REGEX, value):
        raise ValueError(
            "Password must be at least 8 characters long, include an uppercase letter, a number, and a special character."
        )
    return value


class User(BaseModel):
    id: int | None = None
    name: str
    username: str
    email: EmailStr
    city: str | None = None
    birthdate: str | None = None
    preferred_language: str
    gender: int
    units: int
    height: int | None = None
    access_type: int
    photo_path: str | None = None
    is_active: int
    first_day_of_week: int = 1
    currency: int
    mfa_enabled: bool = False
    mfa_secret: str | None = None

    model_config = {"from_attributes": True}


class UserCreate(User):
    password: str

    @field_validator("password")
    def validate_password_field(cls, value):
        return validate_password(value)


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


class UserEditPassword(BaseModel):
    password: str

    @field_validator("password")
    def validate_password_field(cls, value):
        return validate_password(value)
