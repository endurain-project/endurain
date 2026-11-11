"""Garmin Connect request and response shapes."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, SecretStr, field_validator

import core.job_status as core_job_status
import modules.garmin.constants as garmin_constants


class GarminLogin(BaseModel):
    """Credentials a user submits to link Garmin Connect."""

    username: str = Field(min_length=1, max_length=250)
    password: SecretStr = Field(min_length=1, max_length=250)
    is_cn: bool = False

    model_config = ConfigDict(extra="forbid")


class MFARequest(BaseModel):
    """The MFA code a user submits to finish a link attempt."""

    mfa_code: str = Field(min_length=1, max_length=32, pattern=r"^[A-Za-z0-9]+$")

    model_config = ConfigDict(extra="forbid")

    @field_validator("mfa_code", mode="before")
    @classmethod
    def _strip_separators(cls, value: object) -> object:
        """Drop the whitespace and dashes a code is pasted or autofilled with, such as ``123 456``."""
        if isinstance(value, str):
            return "".join(value.split()).replace("-", "")
        return value


class GarminLinkStatus(core_job_status.JobStatus):
    """Where a Garmin Connect link attempt is.

    Attributes:
        kind: Always ``garmin_link``.
        mfa_required: ``true`` while the login waits for a code the user submits through ``POST /garmin/mfa``;
            ``status`` is ``running`` then.
        error_code: Why the attempt failed; set only when ``status`` is ``failed``.
    """

    kind: Literal["garmin_link"]
    mfa_required: bool = Field(default=False, description="The login waits for an MFA code")
    error_code: garmin_constants.LinkFailure | None = Field(default=None, description="Why the attempt failed")


class GarminSyncStatus(core_job_status.JobStatus):
    """Where a queued Garmin Connect gear or health sync is.

    Attributes:
        kind: What the sync pulls, as its job kind.
    """

    kind: Literal["garmin_sync_gear", "garmin_sync_health"]
