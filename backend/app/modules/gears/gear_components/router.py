"""Gear components API router endpoints."""

from collections.abc import Callable
from typing import Annotated

from fastapi import APIRouter, Depends, Header, Request, Response, Security, status
from sqlalchemy.orm import Session

import core.database as core_database
import core.dependencies as core_dependencies
import core.etag as core_etag
import core.rate_limit as core_rate_limit
import modules.auth.dependencies as auth_dependencies
import modules.gears.gear_components.schema as gear_components_schema
import modules.gears.gear_components.service as gear_components_service

router = APIRouter()


@router.get(
    "/types",
    response_model=gear_components_schema.GearComponentTypesRead,
)
def read_gear_component_types(
    _check_scopes: Annotated[Callable, Security(auth_dependencies.check_scopes, scopes=["gears:read"])],
) -> gear_components_schema.GearComponentTypesRead:
    """Retrieve the valid component types, grouped by gear type."""
    return gear_components_service.read_component_types()


@router.get(
    "",
    response_model=list[gear_components_schema.GearComponentRead] | None,
)
def read_gear_components(
    _check_scopes: Annotated[Callable, Security(auth_dependencies.check_scopes, scopes=["gears:read"])],
    token_user_id: Annotated[int, Depends(auth_dependencies.get_sub_from_access_token)],
    db: Annotated[Session, Depends(core_database.get_db)],
) -> list[gear_components_schema.GearComponentRead] | None:
    """Retrieve up to 200 of the authenticated user's gear components."""
    return gear_components_service.list_gear_components(token_user_id, db)


@router.get(
    "/gear_id/{gear_id}",
    response_model=list[gear_components_schema.GearComponentRead] | None,
)
def read_gear_components_gear_id(
    gear_id: core_dependencies.PositiveId,
    _check_scopes: Annotated[Callable, Security(auth_dependencies.check_scopes, scopes=["gears:read"])],
    token_user_id: Annotated[int, Depends(auth_dependencies.get_sub_from_access_token)],
    db: Annotated[Session, Depends(core_database.get_db)],
    active: bool | None = None,
) -> list[gear_components_schema.GearComponentRead] | None:
    """Retrieve up to 200 of a gear's components with the distance and time each has accumulated."""
    return gear_components_service.list_components_for_gear(gear_id, token_user_id, db, active=active)


@router.post(
    "",
    response_model=gear_components_schema.GearComponentRead,
    status_code=status.HTTP_201_CREATED,
)
@core_rate_limit.limiter.limit(core_rate_limit.WRITE)
def create_gear_component(
    request: Request,
    gear_component: gear_components_schema.GearComponentCreate,
    _check_scopes: Annotated[Callable, Security(auth_dependencies.check_scopes, scopes=["gears:write"])],
    token_user_id: Annotated[int, Depends(auth_dependencies.get_sub_from_access_token)],
    db: Annotated[Session, Depends(core_database.get_db)],
) -> gear_components_schema.GearComponentRead:
    """Create a component on one of the authenticated user's gears."""
    return gear_components_service.create_gear_component(gear_component, token_user_id, db)


@router.patch(
    "/{gear_component_id}",
    response_model=gear_components_schema.GearComponentRead,
)
@core_rate_limit.limiter.limit(core_rate_limit.WRITE)
def edit_gear_component(
    request: Request,
    gear_component_id: core_dependencies.PositiveId,
    gear_component: gear_components_schema.GearComponentUpdate,
    _check_scopes: Annotated[Callable, Security(auth_dependencies.check_scopes, scopes=["gears:write"])],
    token_user_id: Annotated[int, Depends(auth_dependencies.get_sub_from_access_token)],
    db: Annotated[Session, Depends(core_database.get_db)],
    response: Response,
    if_match: Annotated[str | None, Header(alias=core_etag.IF_MATCH_HEADER)] = None,
) -> gear_components_schema.GearComponentRead:
    """Update one of the authenticated user's gear components.

    Applies a partial update: only fields present in the request body are
    changed, so omit a field to leave it untouched and send an explicit
    null to clear a nullable field (e.g. `retired_date`).

    The retired/active invariant is enforced server-side: while
    `retired_date` is set the component is always inactive (`active` is
    forced to false); while it is null the submitted `active` value is
    honoured. Reactivating a retired component therefore requires clearing
    `retired_date` and setting `active` to true in the same request.

    Send ``If-Match`` with the component's ``version`` as an ETag to make the write
    conditional; a stale tag is refused with 412.
    """
    updated = gear_components_service.edit_gear_component(
        gear_component_id, gear_component, token_user_id, db, if_match=if_match
    )
    response.headers["ETag"] = core_etag.format_etag(updated.version)
    return updated


@router.delete(
    "/{gear_component_id}",
    response_model=None,
    status_code=status.HTTP_204_NO_CONTENT,
)
@core_rate_limit.limiter.limit(core_rate_limit.WRITE)
def delete_component_gear(
    request: Request,
    gear_component_id: core_dependencies.PositiveId,
    _check_scopes: Annotated[Callable, Security(auth_dependencies.check_scopes, scopes=["gears:write"])],
    token_user_id: Annotated[int, Depends(auth_dependencies.get_sub_from_access_token)],
    db: Annotated[Session, Depends(core_database.get_db)],
) -> None:
    """Delete one of the authenticated user's gear components."""
    gear_components_service.delete_gear_component(token_user_id, gear_component_id, db)
