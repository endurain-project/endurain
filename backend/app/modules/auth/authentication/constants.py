"""Authentication constants."""

from datetime import timedelta
from typing import Final

#: How often an API key's last-used time is stamped at most, so a key reading data does not write a row per request.
API_KEY_LAST_USED_INTERVAL: Final[timedelta] = timedelta(minutes=5)
