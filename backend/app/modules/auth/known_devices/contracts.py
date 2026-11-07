"""Data shapes the known-devices package returns to its peers."""

from dataclasses import dataclass


@dataclass(frozen=True)
class SignInRecord:
    """The outcome of recording a sign-in against the user's known devices.

    Attributes:
        device_id: The device id the client must keep: the web app in its cookie, the mobile app in its storage.
        new_device: Whether the sign-in was announced as one from a new device.
    """

    device_id: str
    new_device: bool
