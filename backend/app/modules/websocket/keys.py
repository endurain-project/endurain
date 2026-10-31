"""Keys for the realtime hint channel.

The channel is server-wide and its key is an opaque string, so a user is addressed as
``user:<id>``. The prefix keeps a user from being confused with any other audience a
future publisher puts on the same channel.
"""

_USER_KEY_PREFIX = "user:"


def user_key(user_id: int) -> str:
    """Build the channel key that addresses one user.

    Args:
        user_id: The target user.

    Returns:
        The key for that user.
    """
    return f"{_USER_KEY_PREFIX}{user_id}"


def parse_user_key(key: str) -> int | None:
    """Read the user a channel key addresses.

    Args:
        key: A key received from the channel, which anyone may have published.

    Returns:
        The user id, or None when the key does not address a user.
    """
    prefix, _, user_id = key.partition(":")
    if f"{prefix}:" != _USER_KEY_PREFIX or not user_id.isascii() or not user_id.isdecimal():
        return None
    return int(user_id)
