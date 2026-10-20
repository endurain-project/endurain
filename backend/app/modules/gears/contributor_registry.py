"""Process-local store of the readers that composition installs for the gears namespace."""

import modules.gears.contributors as gears_contributors

_readers: gears_contributors.GearReaders | None = None


def register(readers: gears_contributors.GearReaders) -> None:
    """Install or replace the gears readers.

    Args:
        readers: The usage and cost readers.
    """
    global _readers
    _readers = readers


def readers() -> gears_contributors.GearReaders:
    """Return the installed gears readers.

    Returns:
        The usage and cost readers.

    Raises:
        RuntimeError: If composition has not installed them, so a missing registration
            fails the request instead of reporting zero usage.
    """
    if _readers is None:
        raise RuntimeError("The gears readers are not installed; call module_registry.configure_gear_contributors()")
    return _readers


def clear() -> None:
    """Remove the installed readers."""
    global _readers
    _readers = None
