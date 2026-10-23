"""Garmin Connect request and response shapes."""

from pydantic import BaseModel, Field, SecretStr

import modules.garmin.constants as garmin_constants


class GarminLogin(BaseModel):
    """Credentials a user submits to link Garmin Connect."""

    username: str = Field(min_length=1, max_length=250)
    password: SecretStr = Field(min_length=1, max_length=250)
    is_cn: bool = False


class MFARequest(BaseModel):
    """The MFA code a user submits to finish a link attempt."""

    mfa_code: str = Field(min_length=1, max_length=32, pattern=r"^[A-Za-z0-9]+$")


class GarminDetail(BaseModel):
    """A human-readable outcome of a Garmin Connect request."""

    detail: str


class GarminLinkStatus(BaseModel):
    """Where a Garmin Connect link attempt is.

    Attributes:
        status: ``pending`` while logging in, ``mfa_required`` when the user must submit a code
            through ``POST /garminconnect/mfa``, then ``completed`` or ``failed``.
        reason: Why the attempt failed; set only when ``status`` is ``failed``.
    """

    status: garmin_constants.LinkStatus
    reason: garmin_constants.LinkFailure | None = None


class GarminSyncStatus(BaseModel):
    """Where a queued Garmin Connect gear or health sync is.

    Attributes:
        kind: What the sync pulls.
        status: ``queued`` until a worker picks it up, ``running``, then ``completed`` or ``failed``.
    """

    kind: garmin_constants.SyncKind
    status: garmin_constants.SyncStatus
