"""Data shapes the known-devices package returns to its peers."""

from dataclasses import dataclass


@dataclass(frozen=True)
class SignInRecord:
    """The outcome of recording a sign-in against the user's known devices.

    Attributes:
        device_id: The device id the browser must keep in its cookie, or None for a mobile client.
        new_device: Whether the sign-in was announced as one from a new device.
    """

    device_id: str | None
    new_device: bool
