"""FastAPI dependencies for the gear routes."""

from typing import Annotated

from fastapi import Depends

import core.dependencies as core_dependencies
import modules.gears.gear.deletion_state_store as deletion_state_store


def get_gear_deletion_state_store(
    state: core_dependencies.PlatformState,
) -> deletion_state_store.GearDeletionStateStore:
    """Return the gear deletion state store over the platform state provider.

    Args:
        state: The platform state provider.

    Returns:
        The deletion state store.
    """
    return deletion_state_store.GearDeletionStateStore(state)


#: The shared state of a queued gear deletion.
GearDeletionStateStoreDep = Annotated[
    deletion_state_store.GearDeletionStateStore, Depends(get_gear_deletion_state_store)
]
