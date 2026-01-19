"""User integrations Pydantic schemas and validators."""

from datetime import datetime
from typing import Any
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StrictBool,
    StrictStr,
    StrictInt,
)


class UsersIntegrationsBase(BaseModel):
    """
    Base schema for user integrations.

    Attributes:
        strava_client_id: Encrypted Strava client ID.
        strava_client_secret: Encrypted Strava client secret.
        strava_state: Temporary state for Strava OAuth flow.
        strava_token: Encrypted Strava access token.
        strava_refresh_token: Encrypted Strava refresh token.
        strava_token_expires_at: Strava token expiration time.
        strava_sync_gear: Enable Strava gear synchronization.
        garminconnect_oauth1: Garmin Connect OAuth1 token
            data.
        garminconnect_oauth2: Garmin Connect OAuth2 token
            data.
        garminconnect_sync_gear: Enable Garmin Connect gear
            synchronization.
    """

    strava_client_id: StrictStr | None = Field(
        None,
        max_length=512,
        description=("Strava client ID encrypted at rest with Fernet key"),
    )
    strava_client_secret: StrictStr | None = Field(
        None,
        max_length=512,
        description=("Strava client secret encrypted at rest with Fernet key"),
    )
    strava_state: StrictStr | None = Field(
        None,
        max_length=45,
        description="Strava temporary state for link process",
    )
    strava_token: StrictStr | None = Field(
        None,
        max_length=512,
        description=(
            "Strava token after link process encrypted at rest with Fernet key"
        ),
    )
    strava_refresh_token: StrictStr | None = Field(
        None,
        max_length=512,
        description=(
            "Strava refresh token after link process "
            "encrypted at rest with Fernet key"
        ),
    )
    strava_token_expires_at: datetime | None = Field(
        None, description="Strava token expiration date"
    )
    strava_sync_gear: StrictBool = Field(
        False, description="Whether Strava gear is to be synced"
    )
    garminconnect_oauth1: dict[str, Any] | None = Field(
        None, description="Garmin OAuth1 token"
    )
    garminconnect_oauth2: dict[str, Any] | None = Field(
        None, description="Garmin OAuth2 token"
    )
    garminconnect_sync_gear: StrictBool = Field(
        False,
        description="Whether Garmin Connect gear is to be synced",
    )

    model_config = ConfigDict(
        from_attributes=True,
        extra="forbid",
        validate_assignment=True,
    )


class UsersIntegrationsCreate(UsersIntegrationsBase):
    """
    Pydantic model for creating user integrations.

    Inherits all attributes from UsersIntegrationsBase.
    """


class UsersIntegrationsUpdate(UsersIntegrationsBase):
    """
    Schema for updating user integrations.

    Inherits all validation from UsersIntegrationsBase.
    All fields are optional for partial updates.
    """


class UsersIntegrationsRead(UsersIntegrationsBase):
    """
    Schema for reading user integrations.

    Attributes:
        id: Unique identifier for the integrations record.
        user_id: Foreign key reference to the user.
    """

    id: StrictInt = Field(..., ge=1, description="Unique identifier for integrations")
    user_id: StrictInt = Field(
        ..., ge=1, description="Foreign key reference to the user"
    )
