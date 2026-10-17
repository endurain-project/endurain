"""Gear components API router endpoints."""

from collections.abc import Callable
from typing import Annotated

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Security,
    status,
)
from sqlalchemy.orm import Session

import core.database as core_database
import modules.auth.dependencies as auth_dependencies
import modules.gears.gear.dependencies as gear_dependencies
import modules.gears.gear_components.crud as gear_components_crud
import modules.gears.gear_components.dependencies as gear_components_dependencies
import modules.gears.gear_components.schema as gear_components_schema

# Define the API router
router = APIRouter()


@router.get(
    "/types",
    response_model=gear_components_schema.GearComponentTypesRead,
    status_code=status.HTTP_200_OK,
)
async def read_gear_component_types(
    _check_scopes: Annotated[
        Callable,
        Security(
            auth_dependencies.check_scopes,
            scopes=["gears:read"],
        ),
    ],
) -> gear_components_schema.GearComponentTypesRead:
    """
    Retrieve valid component type lists.

    Args:
        _check_scopes: Validates gears:read scope.

    Returns:
        Component types grouped by gear type.

    Raises:
        HTTPException: If unauthorized.
    """
    return gear_components_schema.GearComponentTypesRead(
        bike=gear_components_schema.BIKE_COMPONENT_TYPES,
        shoes=gear_components_schema.SHOES_COMPONENT_TYPES,
        racquet=(gear_components_schema.RACQUET_COMPONENT_TYPES),
        windsurf=(gear_components_schema.WINDSURF_COMPONENT_TYPES),
    )


@router.get(
    "",
    response_model=(list[gear_components_schema.GearComponentRead] | None),
    status_code=status.HTTP_200_OK,
)
async def read_gear_components(
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
) -> list[gear_components_schema.GearComponentRead] | None:
    """
    Retrieve all gear components for a user.

    Args:
        _check_scopes: Validates gears:read scope.
        token_user_id: Authenticated user ID.
        db: Database session.

    Returns:
        List of gear component records or None.

    Raises:
        HTTPException: If unauthorized.
    """
    return gear_components_crud.get_gear_components_user(
        token_user_id,
        db,
    )


@router.get(
    "/gear_id/{gear_id}",
    response_model=(list[gear_components_schema.GearComponentRead] | None),
    status_code=status.HTTP_200_OK,
)
async def read_gear_components_gear_id(
    gear_id: int,
    _validate_gear_id: Annotated[
        Callable,
        Depends(
            gear_dependencies.validate_gear_id,
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
    active: bool | None = None,
) -> list[gear_components_schema.GearComponentRead] | None:
    """
    Retrieve gear components by gear ID.

    Args:
        gear_id: Gear ID to filter by.
        validate_gear_id: Validates gear ID.
        _check_scopes: Validates gears:read scope.
        token_user_id: Authenticated user ID.
        db: Database session.
        active: Optional active-status filter.

    Returns:
        List of gear component records or None.

    Raises:
        HTTPException: If unauthorized.
    """
    components = gear_components_crud.get_gear_components_user_by_gear_id(
        token_user_id,
        gear_id,
        db,
        active=active,
    )
    if not components:
        return components

    stats = gear_components_crud.get_components_activity_stats(
        gear_id,
        db,
    )

    result: list[gear_components_schema.GearComponentRead] = []
    for comp in components:
        comp_stats = stats.get(comp.id, {})
        comp_read = comp.model_copy(
            update={
                "current_distance": comp_stats.get("distance", 0),
                "current_time": comp_stats.get("time", 0),
            }
        )
        result.append(comp_read)

    return result


@router.post(
    "",
    response_model=gear_components_schema.GearComponentRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_gear_component(
    gear_component: gear_components_schema.GearComponentCreate,
    _check_scopes: Annotated[
        Callable,
        Security(
            auth_dependencies.check_scopes,
            scopes=["gears:write"],
        ),
    ],
    _verify_gear_type: Annotated[
        Callable,
        Security(
            gear_components_dependencies.validate_gear_component_type,
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
) -> gear_components_schema.GearComponentRead:
    """
    Create a new gear component.

    Args:
        gear_component: Gear component data.
        _check_scopes: Validates gears:write scope.
        verify_gear_type: Validates component type.
        token_user_id: Authenticated user ID.
        db: Database session.

    Returns:
        Created gear component record.

    Raises:
        HTTPException: If unauthorized or invalid
            component type.
    """
    return gear_components_crud.create_gear_component(
        gear_component,
        token_user_id,
        db,
    )


@router.put(
    "",
    response_model=gear_components_schema.GearComponentRead,
    status_code=status.HTTP_200_OK,
)
async def edit_gear_component(
    gear_component: gear_components_schema.GearComponentUpdate,
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
) -> gear_components_schema.GearComponentRead:
    """
    Update an existing gear component.

    Applies a partial update: only fields present in the request body are
    changed, so omit a field to leave it untouched and send an explicit
    null to clear a nullable field (e.g. `retired_date`).

    The retired/active invariant is enforced server-side: while
    `retired_date` is set the component is always inactive (`active` is
    forced to false); while it is null the submitted `active` value is
    honoured. Reactivating a retired component therefore requires clearing
    `retired_date` and setting `active` to true in the same request.

    Args:
        gear_component: Updated component data.
        _check_scopes: Validates gears:write scope.
        token_user_id: Authenticated user ID.
        db: Database session.

    Returns:
        Updated gear component record.

    Raises:
        HTTPException: If not found, forbidden,
            or invalid dates.
    """
    if (
        gear_component.retired_date is not None
        and gear_component.purchase_date is not None
        and gear_component.retired_date <= gear_component.purchase_date
    ):
        raise HTTPException(
            status_code=(status.HTTP_400_BAD_REQUEST),
            detail=("Retired date must be after purchase date"),
        )

    return gear_components_crud.edit_gear_component(
        gear_component,
        token_user_id,
        db,
    )


@router.delete(
    "/{gear_component_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_component_gear(
    gear_component_id: int,
    _validate_id: Annotated[
        Callable,
        Depends(
            gear_components_dependencies.validate_gear_component_id,
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
    Delete a gear component by ID.

    Args:
        gear_component_id: Component ID to delete.
        validate_id: Validates component ID.
        _check_scopes: Validates gears:write scope.
        token_user_id: Authenticated user ID.
        db: Database session.

    Returns:
        None.

    Raises:
        HTTPException: If not found, forbidden,
            or unauthorized.
    """
    gear_components_crud.delete_gear_component(
        token_user_id,
        gear_component_id,
        db,
    )
