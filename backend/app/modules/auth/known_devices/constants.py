"""Constants for known devices."""

#: Random bytes in a device id; base64url without padding makes it 43 characters.
DEVICE_ID_BYTES = 32
#: A device is forgotten this many days after its last sign-in, and its cookie lasts as long. 400 days is the
#: longest lifetime browsers allow a cookie.
DEVICE_RETENTION_DAYS = 400
