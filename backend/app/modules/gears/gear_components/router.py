"""Gear components API router endpoints."""

from typing import Annotated

from fastapi import APIRouter, Depends, Header, Request, Response, Security, status

import core.dependencies as core_dependencies
import core.etag as core_etag
import core.pagination as core_pagination
import core.rate_limit as core_rate_limit
import modules.auth.dependencies as auth_dependencies
import modules.gears.gear_components.schema as gear_components_schema
import modules.gears.gear_components.service as gear_components_service

router = APIRouter()


@router.get(
    "/types",
    response_model=gear_components_schema.GearComponentTypesRead,
    dependencies=[Security(auth_dependencies.check_scopes, scopes=["gears:read"])],
)
def read_gear_component_types() -> gear_components_schema.GearComponentTypesRead:
    """Retrieve the valid component types, grouped by gear type."""
    return gear_components_service.read_component_types()


@router.get(
    "",
    response_model=core_pagination.Page[gear_components_schema.GearComponentRead],
    dependencies=[Security(auth_dependencies.check_scopes, scopes=["gears:read"])],
)
def read_gear_components(
    token_user_id: auth_dependencies.CurrentUserId,
    db: core_dependencies.DbSession,
    page: Annotated[core_pagination.PageParams, Depends(core_pagination.child_page_params)],
) -> core_pagination.Page[gear_components_schema.GearComponentRead]:
    """Retrieve one page of the authenticated user's gear components, with the total."""
    return gear_components_service.list_gear_components(
        token_user_id, db, page_number=page.page_number, num_records=page.num_records
    )


@router.get(
    "/gears/{gear_id}",
    response_model=core_pagination.Page[gear_components_schema.GearComponentRead],
    dependencies=[Security(auth_dependencies.check_scopes, scopes=["gears:read"])],
)
def read_gear_components_gear_id(
    gear_id: core_dependencies.PositiveId,
    token_user_id: auth_dependencies.CurrentUserId,
    db: core_dependencies.DbSession,
    page: Annotated[core_pagination.PageParams, Depends(core_pagination.child_page_params)],
    active: bool | None = None,
) -> core_pagination.Page[gear_components_schema.GearComponentRead]:
    """Retrieve one page of a gear's components with the distance and time each has accumulated."""
    return gear_components_service.list_components_for_gear(
        gear_id, token_user_id, db, active=active, page_number=page.page_number, num_records=page.num_records
    )


@router.post(
    "",
    response_model=gear_components_schema.GearComponentRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Security(auth_dependencies.check_scopes, scopes=["gears:write"])],
)
@core_rate_limit.limiter.limit(core_rate_limit.WRITE)
def create_gear_component(
    request: Request,
    gear_component: gear_components_schema.GearComponentCreate,
    token_user_id: auth_dependencies.CurrentUserId,
    db: core_dependencies.DbSession,
) -> gear_components_schema.GearComponentRead:
    """Create a component on one of the authenticated user's gears."""
    return gear_components_service.create_gear_component(gear_component, token_user_id, db)


@router.patch(
    "/{gear_component_id}",
    response_model=gear_components_schema.GearComponentRead,
    dependencies=[Security(auth_dependencies.check_scopes, scopes=["gears:write"])],
)
@core_rate_limit.limiter.limit(core_rate_limit.WRITE)
def edit_gear_component(
    request: Request,
    gear_component_id: core_dependencies.PositiveId,
    gear_component: gear_components_schema.GearComponentUpdate,
    token_user_id: auth_dependencies.CurrentUserId,
    db: core_dependencies.DbSession,
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
    dependencies=[Security(auth_dependencies.check_scopes, scopes=["gears:write"])],
)
@core_rate_limit.limiter.limit(core_rate_limit.WRITE)
def delete_component_gear(
    request: Request,
    gear_component_id: core_dependencies.PositiveId,
    token_user_id: auth_dependencies.CurrentUserId,
    db: core_dependencies.DbSession,
) -> None:
    """Delete one of the authenticated user's gear components."""
    gear_components_service.delete_gear_component(token_user_id, gear_component_id, db)
