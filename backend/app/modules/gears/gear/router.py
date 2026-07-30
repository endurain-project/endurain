"""Gear API router endpoints."""

from collections.abc import Callable
from typing import Annotated

from fastapi import (
    APIRouter,
    Depends,
    Query,
    Security,
    status,
)
from sqlalchemy.orm import Session

import core.database as core_database
import core.dependencies as core_dependencies
import modules.auth.dependencies as auth_dependencies
import modules.gears.gear.crud as gears_crud
import modules.gears.gear.dependencies as gears_dependencies
import modules.gears.gear.schema as gears_schema

# Define the API router
router = APIRouter()


@router.get(
    "",
    response_model=gears_schema.GearsListResponse,
    status_code=status.HTTP_200_OK,
)
async def read_gears_user_all_pagination(
    _validate_pagination_values_on_query: Annotated[
        Callable,
        Depends(core_dependencies.validate_pagination_values_on_query),
    ],
    _check_scopes: Annotated[
        Callable,
        Security(
            auth_dependencies.check_scopes,
            scopes=["gears:read"],
        ),
    ],
    token_user_id: Annotated[
        int,
        Depends(
            auth_dependencies.get_sub_from_access_token,
        ),
    ],
    db: Annotated[
        Session,
        Depends(core_database.get_db),
    ],
    page_number: Annotated[
        int | None,
        Query(
            description="Pagination page number",
        ),
    ] = None,
    num_records: Annotated[
        int | None,
        Query(
            description="Records per page",
        ),
    ] = None,
    show_inactive: Annotated[
        bool | None,
        Query(
            description="Filter by inactive status",
        ),
    ] = None,
) -> gears_schema.GearsListResponse:
    """
    Retrieve paginated gear records for a user.

    Args:
        _validate_pagination_values_on_query:
            Validates pagination query params.
        _check_scopes: Validates gears:read scope.
        token_user_id: Authenticated user ID.
        db: Database session.
        page_number: Optional page number.
        num_records: Optional records per page.
        show_inactive: Optional inactive filter.

    Returns:
        GearsListResponse with paginated records.

    Raises:
        HTTPException: If unauthorized or invalid
            parameters.
    """
    total = gears_crud.get_gears_number(token_user_id, db, show_inactive)
    gears = gears_crud.get_gear_users_with_pagination(
        token_user_id,
        db,
        page_number,
        num_records,
        show_inactive,
    )

    return gears_schema.GearsListResponse(
        total=total,
        num_records=num_records,
        page_number=page_number,
        records=gears,
    )


@router.get(
    "/id/{gear_id}",
    response_model=(gears_schema.GearDetailRead | None),
    status_code=status.HTTP_200_OK,
)
async def read_gear_id(
    gear_id: int,
    _validate_id: Annotated[
        Callable,
        Depends(
            gears_dependencies.validate_gear_id,
        ),
    ],
    _check_scopes: Annotated[
        Callable,
        Security(
            auth_dependencies.check_scopes,
            scopes=["gears:read"],
        ),
    ],
    token_user_id: Annotated[
        int,
        Depends(
            auth_dependencies.get_sub_from_access_token,
        ),
    ],
    db: Annotated[
        Session,
        Depends(core_database.get_db),
    ],
) -> gears_schema.GearDetailRead | None:
    """
    Retrieve a gear by ID with computed stats.

    Args:
        gear_id: Gear ID to retrieve.
        validate_id: Validates gear ID exists.
        _check_scopes: Validates gears:read scope.
        token_user_id: Authenticated user ID.
        db: Database session.

    Returns:
        GearDetailRead with stats, or None.

    Raises:
        HTTPException: If unauthorized.
    """
    gear = gears_crud.get_gear_user_by_id(
        token_user_id,
        gear_id,
        db,
    )
    if gear is None:
        return None

    activity_stats = gears_crud.get_gear_activity_stats(
        gear_id,
        db,
    )
    components_cost = gears_crud.get_gear_components_total_cost(
        gear_id,
        token_user_id,
        db,
    )
    initial_kms_m = (
        float(
            gear.initial_kms or 0,
        )
        * 1000
    )

    return gears_schema.GearDetailRead(
        **gear.model_dump(),
        total_distance=(activity_stats["total_distance"] + initial_kms_m),
        total_time=(activity_stats["total_time"]),
        total_components_cost=(components_cost),
    )


@router.get(
    "/nickname/contains/{nickname}",
    response_model=list[gears_schema.GearRead],
    status_code=status.HTTP_200_OK,
)
async def read_gear_user_contains_nickname(
    nickname: str,
    _check_scopes: Annotated[
        Callable,
        Security(
            auth_dependencies.check_scopes,
            scopes=["gears:read"],
        ),
    ],
    token_user_id: Annotated[
        int,
        Depends(
            auth_dependencies.get_sub_from_access_token,
        ),
    ],
    db: Annotated[
        Session,
        Depends(core_database.get_db),
    ],
) -> list[gears_schema.GearRead]:
    """
    Retrieve gears matching a nickname substring.

    Args:
        nickname: Substring to search for.
        _check_scopes: Validates gears:read scope.
        token_user_id: Authenticated user ID.
        db: Database session.

    Returns:
        List of GearRead matching the nickname.

    Raises:
        HTTPException: If unauthorized.
    """
    return gears_crud.get_gear_user_contains_nickname(
        token_user_id,
        nickname,
        db,
    )


@router.get(
    "/nickname/{nickname}",
    response_model=gears_schema.GearRead | None,
    status_code=status.HTTP_200_OK,
)
async def read_gear_user_by_nickname(
    nickname: str,
    _check_scopes: Annotated[
        Callable,
        Security(
            auth_dependencies.check_scopes,
            scopes=["gears:read"],
        ),
    ],
    token_user_id: Annotated[
        int,
        Depends(
            auth_dependencies.get_sub_from_access_token,
        ),
    ],
    db: Annotated[
        Session,
        Depends(core_database.get_db),
    ],
) -> gears_schema.GearRead | None:
    """
    Retrieve a gear by exact nickname for a user.

    Args:
        nickname: Gear nickname to match.
        _check_scopes: Validates gears:read scope.
        token_user_id: Authenticated user ID.
        db: Database session.

    Returns:
        GearRead if found, None otherwise.

    Raises:
        HTTPException: If unauthorized.
    """
    return gears_crud.get_gear_user_by_nickname(
        token_user_id,
        nickname,
        db,
    )


@router.get(
    "/type/{gear_type}",
    response_model=list[gears_schema.GearRead],
    status_code=status.HTTP_200_OK,
)
async def read_gear_user_by_type(
    gear_type: int,
    _validate_type: Annotated[
        Callable,
        Depends(
            gears_dependencies.validate_gear_type,
        ),
    ],
    _check_scopes: Annotated[
        Callable,
        Security(
            auth_dependencies.check_scopes,
            scopes=["gears:read"],
        ),
    ],
    token_user_id: Annotated[
        int,
        Depends(
            auth_dependencies.get_sub_from_access_token,
        ),
    ],
    db: Annotated[
        Session,
        Depends(core_database.get_db),
    ],
) -> list[gears_schema.GearRead]:
    """
    Retrieve gears by type for a user.

    Args:
        gear_type: Gear type identifier.
        validate_type: Validates gear type value.
        _check_scopes: Validates gears:read scope.
        token_user_id: Authenticated user ID.
        db: Database session.

    Returns:
        List of GearRead matching the type.

    Raises:
        HTTPException: If unauthorized or invalid
            type.
    """
    return gears_crud.get_gear_by_type_and_user(
        gear_type,
        token_user_id,
        db,
    )


@router.post(
    "",
    response_model=gears_schema.GearRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_gear(
    gear: gears_schema.GearCreate,
    _check_scopes: Annotated[
        Callable,
        Security(
            auth_dependencies.check_scopes,
            scopes=["gears:write"],
        ),
    ],
    token_user_id: Annotated[
        int,
        Depends(
            auth_dependencies.get_sub_from_access_token,
        ),
    ],
    db: Annotated[
        Session,
        Depends(core_database.get_db),
    ],
) -> gears_schema.GearRead:
    """
    Create a new gear for the authenticated user.

    Args:
        gear: Gear data to create.
        _check_scopes: Validates gears:write scope.
        token_user_id: Authenticated user ID.
        db: Database session.

    Returns:
        Created GearRead record.

    Raises:
        HTTPException: If unauthorized or gear
            already exists.
    """
    return gears_crud.create_gear(
        gear,
        token_user_id,
        db,
    )


@router.put(
    "",
    response_model=gears_schema.GearRead,
    status_code=status.HTTP_200_OK,
)
async def edit_gear(
    gear: gears_schema.GearUpdate,
    _check_scopes: Annotated[
        Callable,
        Security(
            auth_dependencies.check_scopes,
            scopes=["gears:write"],
        ),
    ],
    token_user_id: Annotated[
        int,
        Depends(
            auth_dependencies.get_sub_from_access_token,
        ),
    ],
    db: Annotated[
        Session,
        Depends(core_database.get_db),
    ],
) -> gears_schema.GearRead:
    """
    Update an existing gear by ID.

    Args:
        gear: Updated gear data.
        _check_scopes: Validates gears:write scope.
        token_user_id: Authenticated user ID.
        db: Database session.

    Returns:
        Updated GearRead record.

    Raises:
        HTTPException: If gear not found, forbidden,
            or unauthorized.
    """
    return gears_crud.edit_gear(
        gear,
        token_user_id,
        db,
    )


@router.delete(
    "/{gear_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_gear(
    gear_id: int,
    _validate_id: Annotated[
        Callable,
        Depends(
            gears_dependencies.validate_gear_id,
        ),
    ],
    _check_scopes: Annotated[
        Callable,
        Security(
            auth_dependencies.check_scopes,
            scopes=["gears:write"],
        ),
    ],
    token_user_id: Annotated[
        int,
        Depends(
            auth_dependencies.get_sub_from_access_token,
        ),
    ],
    db: Annotated[
        Session,
        Depends(core_database.get_db),
    ],
) -> None:
    """
    Delete a gear by ID.

    Args:
        gear_id: Gear ID to delete.
        validate_id: Validates gear ID exists.
        _check_scopes: Validates gears:write scope.
        token_user_id: Authenticated user ID.
        db: Database session.

    Returns:
        None.

    Raises:
        HTTPException: If gear not found, forbidden,
            or unauthorized.
    """
    gears_crud.delete_gear(gear_id, token_user_id, db)
