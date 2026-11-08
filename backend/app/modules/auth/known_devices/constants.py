"""Constants for known devices."""

from datetime import timedelta

#: Random bytes in a device id; base64url without padding makes it 43 characters.
DEVICE_ID_BYTES = 32
#: A device is forgotten this many days after its last sign-in, and its cookie lasts as long. 400 days is the
#: longest lifetime browsers allow a cookie.
DEVICE_RETENTION_DAYS = 400
#: An account this young signs in from its first device without the new-device announcement: the owner has just
#: created it, so there is nothing to warn about. An older account with no device (never signed in, or all devices
#: forgotten) announces its first one, since the sign-in may not be the owner's.
FIRST_DEVICE_GRACE = timedelta(hours=24)
