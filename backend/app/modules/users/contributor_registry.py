"""Process-local store of the callbacks that composition installs for the users namespace."""

import modules.users.contributors as users_contributors
import modules.users.users_profile.contracts as users_profile_contracts

_erasers: users_contributors.UserErasers | None = None
_lifecycle_hooks: users_contributors.UserLifecycleHooks | None = None
_profile_readers: users_contributors.ProfileReaders | None = None
_profile_sections: dict[str, users_profile_contracts.ProfileSection] = {}


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


def register_lifecycle_hooks(hooks: users_contributors.UserLifecycleHooks) -> None:
    """Install or replace the user lifecycle hooks.

    Args:
        hooks: The staging other modules answer for a created or edited user.
    """
    global _lifecycle_hooks
    _lifecycle_hooks = hooks


def lifecycle_hooks() -> users_contributors.UserLifecycleHooks:
    """Return the installed user lifecycle hooks.

    Returns:
        The staging other modules answer for a created or edited user.

    Raises:
        RuntimeError: If composition has not installed them, so a missing registration
            fails the write instead of leaving the user without its per-user rows.
    """
    if _lifecycle_hooks is None:
        raise RuntimeError(
            "The users lifecycle hooks are not installed; call module_registry.configure_user_contributors()"
        )
    return _lifecycle_hooks


def register_profile_readers(readers: users_contributors.ProfileReaders) -> None:
    """Install or replace the profile readers.

    Args:
        readers: The reads other modules answer for the profile overview.
    """
    global _profile_readers
    _profile_readers = readers


def profile_readers() -> users_contributors.ProfileReaders:
    """Return the installed profile readers.

    Returns:
        The reads other modules answer for the profile overview.

    Raises:
        RuntimeError: If composition has not installed them.
    """
    if _profile_readers is None:
        raise RuntimeError(
            "The users profile readers are not installed; call module_registry.configure_user_contributors()"
        )
    return _profile_readers


def register_profile_section(section: users_profile_contracts.ProfileSection) -> None:
    """Add a profile section; sections run in the order they are registered.

    Args:
        section: What a module contributes to the profile export and import.

    Raises:
        ValueError: If a section with the same key is already registered.
    """
    if section.key in _profile_sections:
        raise ValueError(f"The profile section {section.key!r} is already registered")
    _profile_sections[section.key] = section


def profile_sections() -> tuple[users_profile_contracts.ProfileSection, ...]:
    """Return the registered profile sections in registration order.

    Returns:
        The sections the export and import run.

    Raises:
        RuntimeError: If composition has registered none, so an export never silently omits them.
    """
    if not _profile_sections:
        raise RuntimeError(
            "The users profile sections are not installed; call module_registry.configure_user_contributors()"
        )
    return tuple(_profile_sections.values())


def clear() -> None:
    """Remove every installed callback."""
    global _erasers, _lifecycle_hooks, _profile_readers
    _erasers = None
    _lifecycle_hooks = None
    _profile_readers = None
    _profile_sections.clear()
