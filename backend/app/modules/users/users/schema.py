"""User schema definitions for request and response models."""

from datetime import date as datetime_date
from enum import Enum
from zoneinfo import available_timezones

from pydantic import (
    BaseModel,
    ConfigDict,
    EmailStr,
    Field,
    StrictBool,
    StrictInt,
    StrictStr,
    field_validator,
)

import modules.server_settings.schema as server_settings_schema


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
        CHINESE_SIMPLIFIED: Simplified Chinese (zh-Hans).
        CHINESE_TRADITIONAL: Traditional Chinese (zh-Hant).
        GERMAN: German (de).
        FRENCH: French (fr).
        GALICIAN: Galician (gl).
        ITALIAN: Italian (it).
        DUTCH: Dutch (nl).
        PORTUGUESE: Portuguese (pt-PT).
        SLOVENIAN: Slovenian (sl).
        SWEDISH: Swedish (sv).
        SPANISH: Spanish (es).
        ENGLISH: English (en).
        POLISH: Polish (pl).
        TURKISH: Turkish (tr).
        UKRAINIAN: Ukrainian (uk).
        ROMANIAN: Romanian (ro).
        NORWEGIAN: Norwegian Bokmål (nb).
        DANISH: Danish (da).
        FINNISH: Finnish (fi).
        CZECH: Czech (cs).
        GREEK: Greek (el).
        HUNGARIAN: Hungarian (hu).
        BULGARIAN: Bulgarian (bg).
        CROATIAN: Croatian (hr).
        SERBIAN: Serbian (sr).
        SLOVAK: Slovak (sk).
        LITHUANIAN: Lithuanian (lt).
        LATVIAN: Latvian (lv).
        ESTONIAN: Estonian (et).
    """

    CATALAN = "ca"
    CHINESE_SIMPLIFIED = "zh-Hans"
    CHINESE_TRADITIONAL = "zh-Hant"
    GERMAN = "de"
    FRENCH = "fr"
    GALICIAN = "gl"
    ITALIAN = "it"
    DUTCH = "nl"
    PORTUGUESE = "pt-PT"
    SLOVENIAN = "sl"
    SWEDISH = "sv"
    SPANISH = "es"
    ENGLISH = "en"
    POLISH = "pl"
    TURKISH = "tr"
    UKRAINIAN = "uk"
    ROMANIAN = "ro"
    NORWEGIAN = "nb"
    DANISH = "da"
    FINNISH = "fi"
    CZECH = "cs"
    GREEK = "el"
    HUNGARIAN = "hu"
    BULGARIAN = "bg"
    CROATIAN = "hr"
    SERBIAN = "sr"
    SLOVAK = "sk"
    LITHUANIAN = "lt"
    LATVIAN = "lv"
    ESTONIAN = "et"


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


def normalize_access_type(access_type: "UserAccessType | str") -> str:
    """
    Return the string value of an access type.

    Accepts either a :class:`UserAccessType` enum member or its raw
    string value and always returns the plain string form (e.g.
    ``"admin"`` or ``"regular"``).

    Args:
        access_type: A ``UserAccessType`` member or its string value.

    Returns:
        The access type as a plain string.
    """
    return access_type.value if isinstance(access_type, UserAccessType) else access_type


class UsersBase(BaseModel):
    """
    Base users schema with common fields.

    Attributes:
        name: User's full name (1-250 chars).
        username: Unique username (1-250 chars, alphanumeric
            and dots).
        email: User's email address (max 250 chars).
        city: User's city (max 250 chars).
        birthdate: User's birthdate.
        preferred_language: Preferred language.
        gender: User's gender.
        units: User units (metric, imperial).
        height: User's height in centimeters (1-300).
        max_heart_rate: Maximum heart rate in bpm (30-250).
        first_day_of_week: First day of the week.
        currency: User currency (euro, dollar, pound).
        timezone: IANA timezone the athlete lives in.
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
        pattern=r"^[a-zA-Z0-9._-]+$",
        description="Unique username (alphanumeric, dots, hyphen, underscore)",
    )
    email: EmailStr = Field(
        ...,
        max_length=250,
        description="User's email address",
    )
    city: StrictStr | None = Field(
        default=None,
        max_length=250,
        description="User's city",
    )
    birthdate: datetime_date | None = Field(
        default=None,
        description="User's birthdate",
    )
    preferred_language: Language = Field(
        default=Language.ENGLISH,
        description="Preferred language",
    )
    gender: Gender = Field(
        default=Gender.UNSPECIFIED,
        description="User's gender",
    )
    units: server_settings_schema.Units = Field(
        default=server_settings_schema.Units.METRIC,
        description="User units (metric, imperial)",
    )
    height: StrictInt | None = Field(
        default=None,
        ge=1,
        le=300,
        description="Height in centimeters",
    )
    max_heart_rate: StrictInt | None = Field(
        default=None,
        ge=30,
        le=250,
        description="Maximum heart rate in bpm",
    )
    first_day_of_week: WeekDay = Field(
        default=WeekDay.MONDAY,
        description="First day of the week",
    )
    currency: server_settings_schema.Currency = Field(
        default=server_settings_schema.Currency.EURO,
        description="User currency (euro, dollar, pound)",
    )
    timezone: StrictStr | None = Field(
        default=None,
        max_length=250,
        description=(
            "IANA timezone the athlete lives in. Used as the fallback for activities "
            "imported without a GPS track, which would otherwise inherit the server's "
            "timezone. Null means not set."
        ),
    )

    model_config = ConfigDict(use_enum_values=True)

    @field_validator("timezone")
    @classmethod
    def _validate_timezone(cls, value: str | None) -> str | None:
        """Reject anything that is not a known IANA timezone name.

        The value is stored and later handed to ``ZoneInfo`` on the backend and
        ``Intl.DateTimeFormat`` in the browser, so an unknown name would surface
        as a runtime error far from the setting that caused it.

        Args:
            value: Candidate timezone name, or None.

        Returns:
            The validated timezone name, or None.

        Raises:
            ValueError: When the name is not a known IANA timezone.
        """
        if value is None:
            return None
        if value not in available_timezones():
            raise ValueError(f"Unknown IANA timezone: {value}")
        return value

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


class Users(UsersBase):
    """
    Complete users schema with administrative fields.

    Note:
        ``mfa_secret`` is intentionally NOT part of any API-facing
        schema. It lives only on the SQLAlchemy model and is
        accessed directly by MFA verification utilities. Including
        it in a Pydantic schema would risk leaking the encrypted
        seed through responses, exports, logs, or future
        ``model_dump`` callers.

    Attributes:
        access_type: User access level.
        photo_path: Path to user's photo.
        active: Whether the user is active.
        mfa_enabled: Whether MFA is enabled.
        email_verified: Whether email is verified.
        pending_admin_approval: Whether pending admin approval.
    """

    access_type: UserAccessType = Field(
        ...,
        description="User access level",
    )
    photo_path: StrictStr | None = Field(
        default=None,
        max_length=250,
        description="Path to user's photo",
    )
    active: StrictBool = Field(
        ...,
        description="Whether the user is active",
    )
    mfa_enabled: StrictBool = Field(
        default=False,
        description="Whether MFA is enabled",
    )
    email_verified: StrictBool = Field(
        default=False,
        description="Whether email is verified",
    )
    pending_admin_approval: StrictBool = Field(
        default=False,
        description="Whether pending admin approval",
    )

    model_config = ConfigDict(
        from_attributes=True,
        extra="forbid",
        validate_assignment=True,
        use_enum_values=True,
    )


class UsersRead(Users):
    """
    Users schema for read operations.

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
        default=0,
        ge=0,
        description="Number of external auth providers linked",
    )


class UsersMe(UsersRead):
    """
    Extended users schema for current user profile.

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
        has_local_password: Whether the account has a local
            password (False for SSO-only accounts).
    """

    is_strava_linked: StrictInt | None = Field(default=None, description="Whether Strava is linked")
    is_garminconnect_linked: StrictInt | None = Field(default=None, description="Whether Garmin Connect is linked")
    default_activity_visibility: StrictStr | None = Field(default=None, description="Default activity visibility")
    hide_activity_start_time: StrictBool | None = Field(default=None, description="Hide activity start time")
    hide_activity_location: StrictBool | None = Field(default=None, description="Hide activity location")
    hide_activity_map: StrictBool | None = Field(default=None, description="Hide activity map")
    hide_activity_hr: StrictBool | None = Field(default=None, description="Hide activity heart rate")
    hide_activity_power: StrictBool | None = Field(default=None, description="Hide activity power")
    hide_activity_cadence: StrictBool | None = Field(default=None, description="Hide activity cadence")
    hide_activity_elevation: StrictBool | None = Field(default=None, description="Hide activity elevation")
    hide_activity_speed: StrictBool | None = Field(default=None, description="Hide activity speed")
    hide_activity_pace: StrictBool | None = Field(default=None, description="Hide activity pace")
    hide_activity_laps: StrictBool | None = Field(default=None, description="Hide activity laps")
    hide_activity_workout_sets_steps: StrictBool | None = Field(
        default=None, description="Hide activity workout sets and steps"
    )
    hide_activity_gear: StrictBool | None = Field(default=None, description="Hide activity gear")
    has_local_password: StrictBool | None = Field(
        default=None,
        description=(
            "Whether the account has a local password set. False"
            " indicates an SSO-only account, in which case"
            " step-up flows must skip the password factor. The"
            " raw password hash is never exposed; only this"
            " derived boolean is returned."
        ),
    )


class UsersSignup(UsersBase):
    """
    Users schema for signup operations.

    Attributes:
        password: User's password (min 8 chars).
    """

    password: StrictStr = Field(
        ...,
        min_length=8,
        max_length=250,
        description="User's password",
    )


class UsersCreate(Users):
    """
    Users schema for admin user creation.

    Attributes:
        password: User's password (min 8 chars).
    """

    password: StrictStr = Field(
        ...,
        min_length=8,
        max_length=250,
        description="User's password",
    )


class UsersEditPassword(BaseModel):
    """
    Schema for password update operations (self-service).

    Requires the caller to prove possession of the current
    password — and an MFA code when MFA is enabled — before
    the new password is accepted. This prevents a stolen
    in-memory access token from being parlayed into permanent
    account takeover.

    Attributes:
        current_password: Caller's existing password.
        password: New password (min 8 chars).
        mfa_code: TOTP or backup code, required when MFA is
            enabled on the account.
    """

    current_password: StrictStr = Field(
        ...,
        min_length=1,
        max_length=250,
        description="Current password (step-up verification)",
    )
    password: StrictStr = Field(
        ...,
        min_length=8,
        max_length=250,
        description="New password",
    )
    mfa_code: StrictStr | None = Field(
        default=None,
        max_length=32,
        description="TOTP or backup code, required when MFA is enabled",
    )
    revoke_other_sessions: StrictBool = Field(
        default=False,
        description=(
            "When true, revoke all of the user's other sessions "
            "(keeping the current one) after the password change. "
            "Use this to evict an attacker when changing a password "
            "because of a suspected compromise."
        ),
    )

    model_config = ConfigDict(
        extra="forbid",
        validate_assignment=True,
    )


class UsersAdminEditPassword(BaseModel):
    """
    Schema for admin password reset operations.

    Admin password resets are authorised by the caller's
    ``users:write`` scope on the admin route, not by knowing the
    target user's current password. Self-service password changes
    must use :class:`UsersEditPassword` instead.

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


class StepUpVerification(BaseModel):
    """
    Generic step-up verification payload.

    Used by sensitive account-level operations (API key
    creation, MFA backup-code regeneration, etc.) to require
    fresh proof of identity beyond a valid access token.

    For SSO-only accounts (no local password set), the password
    field may be omitted and the password check is skipped — see
    :func:`modules.auth._internal.services.step_up_service.verify_step_up_credentials`
    and ``docs/developer-guide/auth-boundary.md`` for the rationale
    and the tracked SSO-only step-up gap.

    Attributes:
        current_password: Caller's existing password. Required
            when the account has a local password; may be
            omitted for SSO-only accounts.
        mfa_code: TOTP or backup code, required when MFA is
            enabled on the account.
    """

    current_password: StrictStr | None = Field(
        default=None,
        min_length=1,
        max_length=250,
        description=("Current password (step-up verification). Required when the account has a local password."),
    )
    mfa_code: StrictStr | None = Field(
        default=None,
        max_length=32,
        description="TOTP or backup code, required when MFA is enabled",
    )

    model_config = ConfigDict(
        extra="forbid",
        validate_assignment=True,
    )


class ProfileUpdate(BaseModel):
    """
    Schema for self-service profile updates.

    Strict allow-list of fields the authenticated user is
    permitted to change on their own account. Administrative
    fields (``access_type``, ``active``, ``mfa_enabled``,
    ``mfa_secret``, ``email_verified``,
    ``pending_admin_approval``) are intentionally excluded —
    accepting them here would allow self-service privilege
    escalation through mass assignment.

    Attributes:
        name: User's full name.
        username: Unique username.
        email: User's email address.
        city: User's city.
        birthdate: User's birthdate.
        preferred_language: Preferred application language.
        gender: User's gender.
        units: Preferred unit system.
        height: User's height in centimeters.
        max_heart_rate: Maximum heart rate in bpm.
        first_day_of_week: First day of the week.
        currency: Preferred currency.
        timezone: IANA timezone the athlete lives in.
        photo_path: Server-issued photo path. Validated to
            stay within the user's own photo directory.
    """

    name: StrictStr | None = Field(default=None, min_length=1, max_length=250)
    username: StrictStr | None = Field(
        default=None,
        min_length=1,
        max_length=250,
        pattern=r"^[a-zA-Z0-9._-]+$",
    )
    email: EmailStr | None = Field(default=None, max_length=250)
    city: StrictStr | None = Field(default=None, max_length=250)
    birthdate: datetime_date | None = None
    preferred_language: Language | None = None
    gender: Gender | None = None
    units: server_settings_schema.Units | None = None
    height: StrictInt | None = Field(default=None, ge=1, le=300)
    max_heart_rate: StrictInt | None = Field(default=None, ge=30, le=250)
    first_day_of_week: WeekDay | None = None
    currency: server_settings_schema.Currency | None = None
    timezone: StrictStr | None = Field(default=None, max_length=250)
    photo_path: StrictStr | None = Field(default=None, max_length=250)

    model_config = ConfigDict(
        from_attributes=True,
        extra="forbid",
        validate_assignment=True,
        use_enum_values=True,
    )

    @field_validator("birthdate", mode="before")
    @classmethod
    def validate_birthdate(cls, value):
        if value is None:
            return None
        if isinstance(value, datetime_date):
            return value.isoformat()
        return value

    @field_validator("timezone")
    @classmethod
    def validate_timezone(cls, value: str | None) -> str | None:
        """Reject anything that is not a known IANA timezone name.

        Mirrors the check on :class:`UsersBase`: the value is later handed to
        ``ZoneInfo`` when stamping GPS-less activities, so an unknown name would
        surface as a runtime error far from the setting that caused it.

        Args:
            value: Candidate timezone name, or None.

        Returns:
            The validated timezone name, or None.

        Raises:
            ValueError: When the name is not a known IANA timezone.
        """
        if value is None:
            return None
        if value not in available_timezones():
            raise ValueError(f"Unknown IANA timezone: {value}")
        return value


class UsersListResponse(BaseModel):
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
        default=None,
        ge=0,
        description="Number of records in this response",
    )
    page_number: StrictInt | None = Field(
        default=None,
        ge=1,
        description="Current page number",
    )
    records: list[UsersRead] = Field(
        ...,
        description="List of user records",
    )

    model_config = ConfigDict(
        from_attributes=True,
        extra="forbid",
        validate_assignment=True,
    )
