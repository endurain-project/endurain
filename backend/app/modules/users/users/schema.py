"""User schema definitions for request and response models."""

from datetime import date as datetime_date
from datetime import datetime
from enum import Enum
from typing import Annotated
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

import core.pagination as core_pagination
import modules.auth.identity_providers.schema as idp_schema
import modules.server_settings.schema as server_settings_schema
import modules.users.users.constants as users_constants


class Gender(Enum):
    """User gender enumeration.

    Attributes:
        MALE: Male gender.
        FEMALE: Female gender.
        UNSPECIFIED: Unspecified or undisclosed gender.
    """

    MALE = "male"
    FEMALE = "female"
    UNSPECIFIED = "unspecified"


class Language(Enum):
    """Supported application languages.

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
    """Days of the week enumeration.

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
    """User access level enumeration.

    Attributes:
        REGULAR: Standard user access.
        ADMIN: Administrative access.
    """

    REGULAR = "regular"
    ADMIN = "admin"


def normalize_access_type(access_type: "UserAccessType | str") -> str:
    """Return the string value of an access type.

    Accepts either a :class:`UserAccessType` enum member or its raw
    string value and always returns the plain string form (e.g.
    ``"admin"`` or ``"regular"``).

    Args:
        access_type: A ``UserAccessType`` member or its string value.

    Returns:
        The access type as a plain string.
    """
    return access_type.value if isinstance(access_type, UserAccessType) else access_type


#: Field types shared by every shape that takes an account's name, username, email address or new password.
UserName = Annotated[StrictStr, Field(min_length=1, max_length=250, description="User's full name")]
UserUsername = Annotated[
    StrictStr,
    Field(
        min_length=1,
        max_length=250,
        pattern=r"^[a-zA-Z0-9._-]+$",
        description="Unique username (alphanumeric, dots, hyphen, underscore)",
    ),
]
UserEmail = Annotated[EmailStr, Field(max_length=250, description="User's email address")]
UserPassword = Annotated[StrictStr, Field(min_length=8, max_length=250, description="User's password")]


class UsersBase(BaseModel):
    """Base users schema with common fields.

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
        weight_units: Weight units override (metric - kg, imperial - lb);
            null follows units.
        height: User's height in centimeters (1-300).
        max_heart_rate: Maximum heart rate in bpm (30-250).
        first_day_of_week: First day of the week.
        currency: User currency (euro, dollar, pound).
        timezone: IANA timezone the athlete lives in.
    """

    name: UserName
    username: UserUsername
    email: UserEmail
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
    weight_units: server_settings_schema.Units | None = Field(
        default=None,
        description="Weight units override (metric - kg, imperial - lb), follows 'units' when null",
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

    # A default is validated too, so an enum default is stored as its value ("en"), not as the member a driver
    # would write by name ("ENGLISH").
    model_config = ConfigDict(use_enum_values=True, validate_default=True)

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
        """Convert birthdate to ISO format string.

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
    """Complete users schema with administrative fields.

    Note:
        ``mfa_secret`` is intentionally NOT part of any API-facing
        schema. It lives only on the SQLAlchemy model and is
        accessed directly by MFA verification utilities. Including
        it in a Pydantic schema would risk leaking the encrypted
        seed through responses, exports, logs, or future
        ``model_dump`` callers.

    Attributes:
        access_type: User access level.
        photo_path: Servable URL of the user's photo, resolved from
            the stored storage key. Read-only: writes are ignored.
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
        max_length=500,
        description="Servable URL of the user's photo (read-only)",
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
    """Users schema for read operations.

    Attributes:
        id: User ID.
        external_auth_count: Number of external auth providers.
        pending_email: Address awaiting confirmation, which replaces ``email`` once confirmed.
        pending_email_expires_at: When the confirmation link for ``pending_email`` expires.
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
    version: StrictInt = Field(default=1, ge=1, description="Optimistic-concurrency counter, also sent as the ETag")
    pending_email: EmailStr | None = Field(
        default=None, description="Email address awaiting confirmation, which replaces the current one once confirmed"
    )
    pending_email_expires_at: datetime | None = Field(
        default=None, description="When the confirmation link for the pending email address expires"
    )


class UserPublicRead(BaseModel):
    """What any signed-in viewer, or an anonymous one on a shared link, may learn about a user.

    A deliberate subset of :class:`UsersRead`: no email, birthdate, access level or account
    state, so a lookup cannot be used to harvest personal data or to probe who is an admin.

    Attributes:
        id: User ID.
        name: User's full name.
        username: Unique username.
        city: User's city.
        photo_path: Servable URL of the user's photo.
    """

    id: StrictInt = Field(..., ge=1, description="User ID")
    name: StrictStr = Field(..., description="User's full name")
    username: StrictStr = Field(..., description="Unique username")
    city: StrictStr | None = Field(default=None, description="User's city")
    photo_path: StrictStr | None = Field(default=None, description="Servable URL of the user's photo")

    model_config = ConfigDict(from_attributes=True, extra="forbid")


#: One page of public user projections, as a search returns them.
UserPublicPage = core_pagination.Page[UserPublicRead]


class UsersEdit(Users):
    """Users schema for an administrative edit.

    The stored columns of a user and nothing a read adds: ``id`` is the path, and
    ``external_auth_count`` and the pending email change are derived. ``photo_path`` and ``mfa_enabled`` are read-only
    projections, so a write ignores them.
    """

    @classmethod
    def from_read(cls, user: "UsersRead") -> "UsersEdit":
        """Build the edit that re-applies a user as stored, for a caller that changes a few fields.

        Args:
            user: The user as read, usually with the changes already applied.

        Returns:
            The same user as an edit.
        """
        return cls.model_validate(
            user.model_dump(
                exclude={"id", "external_auth_count", "version", "pending_email", "pending_email_expires_at"}
            )
        )


class UsersMe(UsersRead):
    """Extended users schema for current user profile.

    Includes privacy settings and integration status.

    Attributes:
        privacy_settings_version: Version of the privacy settings, for ``If-Match``.
        integrations_version: Version of the integrations, for ``If-Match`` when the Strava client is set.
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
            password (False for accounts that sign in through an
            identity provider).
    """

    privacy_settings_version: StrictInt | None = Field(
        default=None, description="Version of the privacy settings, sent back in If-Match when they are edited"
    )
    integrations_version: StrictInt | None = Field(
        default=None,
        description="Version of the integrations, sent back in If-Match when the Strava client is set",
    )
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
    has_local_password: StrictBool = Field(
        ...,
        description=(
            "Whether the account has a local password set. False"
            " indicates an account that signs in through an identity"
            " provider; its step-up proves a fresh sign-in with that"
            " provider instead of a password. The raw password hash"
            " is never exposed; only this derived boolean is returned."
        ),
    )


class UsersSignup(BaseModel):
    """Users schema for a public sign-up request: only what an account needs.

    The rest of the profile starts from the ``UsersBase`` defaults and is edited after signing in.

    Attributes:
        name: User's full name (1-250 chars).
        username: Unique username (1-250 chars, alphanumeric and dots).
        email: User's email address (max 250 chars).
        password: User's password (min 8 chars). Absent when the password is chosen at email verification.
        preferred_language: Language of the account's emails and interface.
    """

    name: UserName
    username: UserUsername
    email: UserEmail
    password: UserPassword | None = None
    preferred_language: Language = Field(
        default=Language.ENGLISH,
        description="Preferred language",
    )

    model_config = ConfigDict(use_enum_values=True, validate_default=True, extra="forbid")


class UsersCreate(Users):
    """Users schema for admin user creation.

    Attributes:
        password: User's password (min 8 chars).
    """

    password: UserPassword


class FirstAdminCreate(BaseModel):
    """The only fields a caller supplies when the first administrator is created.

    The access level and account state are not here: the users service sets them.

    Attributes:
        name: User's full name.
        username: Unique username.
        email: User's email address.
        password: User's password (min 8 chars; the administrator policy applies on top).
    """

    name: UserName
    username: UserUsername
    email: UserEmail
    password: UserPassword

    model_config = ConfigDict(extra="forbid")


class UsersEditPassword(BaseModel):
    """Schema for password update operations (self-service).

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


class UsersEmailLookup(BaseModel):
    """Schema for looking a user up by email address.

    Attributes:
        email: Email address to search for, case-insensitive.
    """

    email: StrictStr = Field(..., min_length=1, max_length=250, description="Email address to search for")

    model_config = ConfigDict(extra="forbid")


class UsersAdminEditPassword(BaseModel):
    """Schema for admin password reset operations.

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


class UserPhotoRead(BaseModel):
    """The photo a user has after an upload.

    Attributes:
        photo_path: Servable URL of the user's photo, or None when none is stored.
    """

    photo_path: StrictStr | None = Field(default=None, description="Servable URL of the user's photo")


class StepUpVerification(BaseModel):
    """Generic step-up verification payload.

    Used by sensitive account-level operations (API key
    creation, MFA backup-code regeneration, etc.) to require
    fresh proof of identity beyond a valid access token.

    An account without a local password (it signs in through an
    identity provider) proves a fresh sign-in with a linked provider
    instead: ``idp_reauth`` carries the ticket from
    ``POST /profile/identity-providers/{idp_id}/step-up``.

    Attributes:
        current_password: Caller's existing password. Required
            when the account has a local password.
        mfa_code: TOTP or backup code, required when MFA is
            enabled on the account.
        idp_reauth: Proof of a fresh identity-provider sign-in. Required
            when the account has no local password.
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

    idp_reauth: idp_schema.IdpReauthProof | None = Field(
        default=None,
        description="Fresh identity-provider sign-in, required when the account has no local password",
    )

    model_config = ConfigDict(
        extra="forbid",
        validate_assignment=True,
    )


class EmailChange(StepUpVerification):
    """Self-service email change, authorised by step-up verification.

    Attributes:
        email: The new email address.
        revoke_other_sessions: Whether to sign out the user's other sessions after the change.
    """

    email: EmailStr = Field(..., max_length=250, description="The new email address")
    revoke_other_sessions: StrictBool = Field(
        default=False,
        description="When true, revoke all of the user's other sessions (keeping the current one) after the change",
    )


class ProfileUpdate(BaseModel):
    """Schema for self-service profile updates.

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
        city: User's city.
        birthdate: User's birthdate.
        preferred_language: Preferred application language.
        gender: User's gender.
        units: Preferred unit system.
        weight_units: Preferred weight units, independent of units; null follows units.
        height: User's height in centimeters.
        max_heart_rate: Maximum heart rate in bpm.
        first_day_of_week: First day of the week.
        currency: Preferred currency.
        timezone: IANA timezone the athlete lives in.

    Note:
        ``email`` is deliberately absent. It is the address password resets go to, so changing
        it needs fresh proof of identity and is :class:`EmailChange`.

        ``photo_path`` is deliberately absent. The photo is a
        server-issued storage key written only by the upload and
        delete endpoints, so accepting it here would let a caller
        repoint their avatar at another user's blob.
    """

    name: StrictStr | None = Field(default=None, min_length=1, max_length=250)
    username: StrictStr | None = Field(
        default=None,
        min_length=1,
        max_length=250,
        pattern=r"^[a-zA-Z0-9._-]+$",
    )
    city: StrictStr | None = Field(default=None, max_length=250)
    birthdate: datetime_date | None = None
    preferred_language: Language | None = None
    gender: Gender | None = None
    units: server_settings_schema.Units | None = None
    weight_units: server_settings_schema.Units | None = None
    height: StrictInt | None = Field(default=None, ge=1, le=300)
    max_heart_rate: StrictInt | None = Field(default=None, ge=30, le=250)
    first_day_of_week: WeekDay | None = None
    currency: server_settings_schema.Currency | None = None
    timezone: StrictStr | None = Field(default=None, max_length=250)

    model_config = ConfigDict(
        from_attributes=True,
        extra="forbid",
        validate_assignment=True,
        use_enum_values=True,
    )

    @field_validator("birthdate", mode="before")
    @classmethod
    def validate_birthdate(cls, value: datetime_date | str | None) -> str | None:
        """Normalize a birthdate to an ISO string.

        Args:
            value: The submitted birthdate, as a date or an ISO string.

        Returns:
            The ISO date string, or None.
        """
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


class UserDeletionStatus(BaseModel):
    """Where a queued account deletion is.

    Attributes:
        status: Lifecycle state of the deletion.
    """

    status: users_constants.DeletionStatus = Field(..., description="Lifecycle state of the account deletion")

    model_config = ConfigDict(extra="forbid")
