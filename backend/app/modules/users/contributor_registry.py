"""Process-local store of the erasers that composition installs for the users namespace."""

import modules.users.contributors as users_contributors

_erasers: users_contributors.UserErasers | None = None


def register(erasers: users_contributors.UserErasers) -> None:
    """Install or replace the users erasers.

    Args:
        erasers: The erasures other modules answer for a deleted account.
    """
    global _erasers
    _erasers = erasers


def erasers() -> users_contributors.UserErasers:
    """Return the installed users erasers.

    Returns:
        The erasures other modules answer for a deleted account.

    Raises:
        RuntimeError: If composition has not installed them, so a missing registration
            fails the deletion instead of leaving the user's data behind.
    """
    if _erasers is None:
        raise RuntimeError("The users erasers are not installed; call module_registry.configure_user_contributors()")
    return _erasers


def clear() -> None:
    """Remove the installed erasers."""
    global _erasers
    _erasers = None
