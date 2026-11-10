"""Known-device API schemas."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, StrictBool, StrictInt

import core.pagination as core_pagination


class KnownDeviceRead(BaseModel):
    """A device the signed-in user is known to sign in from.

    Attributes:
        id: Device ID, as the forget route takes it.
        browser: Browser of the last sign-in, or None for a device registered before it was recorded.
        operating_system: Operating system of the last sign-in, or None as above.
        device_type: Type of device (Mobile, Tablet, PC) of the last sign-in, or None as above.
        created_at: When the device was first registered under the current security generation.
        last_seen_at: When the user last signed in from the device.
        current: Whether the request comes from this device.
    """

    model_config = ConfigDict(from_attributes=True)

    id: StrictInt = Field(..., ge=1, description="Device ID")
    browser: str | None = Field(None, description="Browser of the last sign-in from the device")
    operating_system: str | None = Field(None, description="Operating system of the last sign-in from the device")
    device_type: str | None = Field(None, description="Device type (Mobile, Tablet, PC) of the last sign-in")
    created_at: datetime = Field(..., description="When the device was registered")
    last_seen_at: datetime = Field(..., description="When the user last signed in from the device")
    current: StrictBool = Field(False, description="Whether the request comes from this device")


#: One page of a user's known devices.
KnownDevicePage = core_pagination.Page[KnownDeviceRead]
