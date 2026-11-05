"""Domain event channels owned by the known-devices package.

Payloads describe the sign-in only: events are persisted, so neither the device id nor its hash is put in one.
"""

from datetime import datetime
from enum import StrEnum
from typing import ClassVar

from jasil.event_versioning import VersionedPayload
from pydantic import ConfigDict

# Published after a sign-in from a device the account was not known to sign in from.
NEW_DEVICE_SIGN_IN = "auth.new_device_sign_in"


class SignInMethod(StrEnum):
    """How the user proved who they are."""

    PASSWORD = "password"
    IDENTITY_PROVIDER = "identity_provider"


class NewDeviceSignInPayload(VersionedPayload):
    """Validated payload for the ``auth.new_device_sign_in`` event.

    Attributes:
        user_id: The user who signed in.
        browser: The browser family the user agent names.
        operating_system: The operating-system family the user agent names.
        device_type: ``PC``, ``Mobile`` or ``Tablet``, from the user agent.
        ip_address: The client address of the sign-in.
        method: How the user signed in.
        signed_in_at: When the sign-in happened.
    """

    model_config = ConfigDict(extra="ignore")

    SCHEMA_VERSION: ClassVar[int] = 1

    user_id: int
    browser: str
    operating_system: str
    device_type: str
    ip_address: str
    method: SignInMethod
    signed_in_at: datetime
