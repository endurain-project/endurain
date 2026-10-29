"""Request-parameter types for the user routes."""

from typing import Annotated

from fastapi import Depends, Path

import core.dependencies as core_dependencies
import modules.users.users.deletion_state_store as users_deletion_state_store

#: A username path segment: required, as long as the column allows, and decoded and lower-cased by the lookup.
Username = Annotated[str, Path(min_length=1, max_length=250)]


def get_user_deletion_state_store(
    state: core_dependencies.PlatformState,
) -> users_deletion_state_store.UserDeletionStateStore:
    """Return the account deletion state store over the platform state provider.

    Args:
        state: The platform state provider.

    Returns:
        The deletion state store.
    """
    return users_deletion_state_store.UserDeletionStateStore(state)


UserDeletionStateStoreDep = Annotated[
    users_deletion_state_store.UserDeletionStateStore, Depends(get_user_deletion_state_store)
]
