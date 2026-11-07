"""Keys for the realtime hint channel.

The channel is server-wide and its key is an opaque string, so a user is addressed as
``user:<id>``. The prefix keeps a user from being confused with any other audience a
future publisher puts on the same channel.
"""

_USER_KEY_PREFIX = "user:"
_CONTROL_KEY_PREFIX = "control:"


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


def control_key(user_id: int) -> str:
    """Build the channel key of the control messages for one user's sockets.

    A control message tells a process what to do with the sockets it holds; it is never forwarded to a client.

    Args:
        user_id: The user whose sockets the message is about.

    Returns:
        The key for that user's control messages.
    """
    return f"{_CONTROL_KEY_PREFIX}{user_id}"


def parse_control_key(key: str) -> int | None:
    """Read the user a control key is about.

    Args:
        key: A key received from the channel, which anyone may have published.

    Returns:
        The user id, or None when the key is not a control key.
    """
    prefix, _, user_id = key.partition(":")
    if f"{prefix}:" != _CONTROL_KEY_PREFIX or not user_id.isascii() or not user_id.isdecimal():
        return None
    return int(user_id)
