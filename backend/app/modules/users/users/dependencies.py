"""Request-parameter types for the user routes."""

from typing import Annotated

from fastapi import Depends, Query
from fastapi.exceptions import RequestValidationError

import core.dependencies as core_dependencies
import core.pagination as core_pagination
import modules.server_settings.integration_service as server_settings_integration
import modules.users.users.deletion_state_store as users_deletion_state_store

#: The fewest characters a username search term may have, so a search cannot enumerate every user.
MIN_SEARCH_TERM_LENGTH = 3


def require_search_term(username: str | None, username_contains: str | None) -> None:
    """Refuse a directory read that names no search term of the minimum length, so the whole list cannot be paged.

    Args:
        username: The exact-username filter, or None.
        username_contains: The contains filter, or None.

    Raises:
        RequestValidationError: When neither filter holds at least ``MIN_SEARCH_TERM_LENGTH`` characters (422).
    """
    if any(term is not None and len(term) >= MIN_SEARCH_TERM_LENGTH for term in (username, username_contains)):
        return
    raise RequestValidationError(
        [
            {
                "type": "missing",
                "loc": ("query", "username_contains"),
                "msg": f"Send username or username_contains with at least {MIN_SEARCH_TERM_LENGTH} characters",
                "input": None,
            }
        ]
    )


def directory_page_params(
    db: core_dependencies.DbSession,
    page_number: Annotated[int | None, Query(ge=1, le=core_pagination.MAX_PAGE_NUMBER)] = None,
    num_records: Annotated[
        int | None, Query(ge=1, description="Page size; defaults to and may not exceed the server's page size")
    ] = None,
) -> core_pagination.PageParams:
    """Resolve the paging window of the user directory from the server's page size.

    Args:
        db: Database session dependency.
        page_number: Requested 1-based page, or None when omitted.
        num_records: Requested page size, or None when omitted.

    Returns:
        The resolved window; an omitted size is the server's ``num_records_per_page``.

    Raises:
        RequestValidationError: When the requested size is above the server's page size (422).
    """
    page_size = server_settings_integration.get_server_settings(db).num_records_per_page
    if num_records is not None and num_records > page_size:
        raise RequestValidationError(
            [
                {
                    "type": "less_than_equal",
                    "loc": ("query", "num_records"),
                    "msg": f"Input should be less than or equal to {page_size}",
                    "input": num_records,
                    "ctx": {"le": page_size},
                }
            ]
        )
    return core_pagination.PageParams(page_number or 1, num_records or page_size)


#: The user directory's paging window, declared as ``page: users_dependencies.DirectoryPage``.
DirectoryPage = Annotated[core_pagination.PageParams, Depends(directory_page_params)]


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
