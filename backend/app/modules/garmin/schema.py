from pydantic import BaseModel

import modules.garmin.link_state_store as garmin_link_state_store


class GarminLogin(BaseModel):
    username: str
    password: str
    is_cn: bool = False


class MFARequest(BaseModel):
    mfa_code: str


class GarminLinkStatus(BaseModel):
    """Where a Garmin Connect link attempt is.

    Attributes:
        status: ``pending`` while logging in, ``mfa_required`` when the user must submit a code
            through ``POST /garminconnect/mfa``, then ``completed`` or ``failed``.
        reason: Why the attempt failed; set only when ``status`` is ``failed``.
    """

    status: garmin_link_state_store.LinkStatus
    reason: garmin_link_state_store.LinkFailure | None = None
