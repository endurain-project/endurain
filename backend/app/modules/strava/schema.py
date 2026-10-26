"""Strava request and response shapes."""

from pydantic import BaseModel, ConfigDict, Field, SecretStr

import modules.strava.constants as strava_constants


class StravaClientCredentials(BaseModel):
    """A user's Strava API application credentials.

    Attributes:
        client_id: The Strava application's client id.
        client_secret: The Strava application's client secret.
    """

    model_config = ConfigDict(extra="forbid")

    client_id: int = Field(gt=0)
    client_secret: SecretStr = Field(min_length=1, max_length=255)


class StravaLinkRequest(BaseModel):
    """The OAuth callback values that complete a Strava link.

    Attributes:
        state: The one-time state stored before the OAuth round-trip.
        code: The authorization code Strava returned.
    """

    model_config = ConfigDict(extra="forbid")

    state: str = Field(min_length=strava_constants.OAUTH_STATE_MIN_LENGTH, max_length=128)
    code: str = Field(min_length=1, max_length=255)


class StravaState(BaseModel):
    """The one-time state the browser round-trips through Strava.

    Attributes:
        state: The opaque state, to be sent to Strava and handed back with the authorization code.
    """

    state: str


class StravaDetail(BaseModel):
    """The outcome of a Strava account request."""

    detail: str


class StravaSyncStatus(BaseModel):
    """Where a queued Strava gear sync or unlink is.

    Attributes:
        kind: What the sync does.
        status: Where it is.
    """

    kind: strava_constants.SyncKind
    status: strava_constants.SyncStatus
