"""Gear API router endpoints."""

from typing import Annotated

from fastapi import APIRouter, Depends, Header, Query, Request, Response, Security, status

import core.dependencies as core_dependencies
import core.etag as core_etag
import core.pagination as core_pagination
import core.rate_limit as core_rate_limit
import modules.auth.dependencies as auth_dependencies
import modules.gears.gear.schema as gears_schema
import modules.gears.gear.service as gears_service

router = APIRouter()


@router.get(
    "",
    response_model=core_pagination.Page[gears_schema.GearRead],
    dependencies=[Security(auth_dependencies.check_scopes, scopes=["gears:read"])],
)
def list_gears(
    token_user_id: auth_dependencies.CurrentUserId,
    db: core_dependencies.DbSession,
    page: Annotated[core_pagination.PageParams, Depends(core_pagination.list_page_params)],
    show_inactive: Annotated[bool | None, Query(description="Filter by inactive status")] = None,
    gear_type: Annotated[gears_schema.GearType | None, Query(description="Keep only gears of this type")] = None,
    nickname_contains: Annotated[
        str | None,
        Query(min_length=1, max_length=250, description="Keep only gears whose nickname contains this text"),
    ] = None,
) -> core_pagination.Page[gears_schema.GearRead]:
    """Retrieve one page of the authenticated user's gears, with the matching total."""
    return gears_service.list_gears(
        token_user_id,
        db,
        page_number=page.page_number,
        num_records=page.num_records,
        show_inactive=show_inactive,
        gear_type=gear_type,
        nickname_contains=nickname_contains,
    )


@router.get(
    "/{gear_id}",
    response_model=gears_schema.GearDetailRead,
    dependencies=[Security(auth_dependencies.check_scopes, scopes=["gears:read"])],
)
def read_gear_id(
    gear_id: core_dependencies.PositiveId,
    token_user_id: auth_dependencies.CurrentUserId,
    db: core_dependencies.DbSession,
    response: Response,
) -> gears_schema.GearDetailRead:
    """Retrieve a gear by ID with its total distance, time and components cost."""
    gear = gears_service.read_gear_detail(gear_id, token_user_id, db)
    # The tag the client echoes back in If-Match when it later saves.
    response.headers["ETag"] = core_etag.format_etag(gear.version)
    return gear


@router.post(
    "",
    response_model=gears_schema.GearRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Security(auth_dependencies.check_scopes, scopes=["gears:write"])],
)
@core_rate_limit.limiter.limit(core_rate_limit.WRITE)
def create_gear(
    request: Request,
    gear: gears_schema.GearCreateRequest,
    token_user_id: auth_dependencies.CurrentUserId,
    db: core_dependencies.DbSession,
) -> gears_schema.GearRead:
    """Create a gear for the authenticated user."""
    return gears_service.create_gear(gear, token_user_id, db)


@router.patch(
    "/{gear_id}",
    response_model=gears_schema.GearRead,
    dependencies=[Security(auth_dependencies.check_scopes, scopes=["gears:write"])],
)
@core_rate_limit.limiter.limit(core_rate_limit.WRITE)
def edit_gear(
    request: Request,
    gear_id: core_dependencies.PositiveId,
    gear: gears_schema.GearUpdate,
    token_user_id: auth_dependencies.CurrentUserId,
    db: core_dependencies.DbSession,
    response: Response,
    if_match: Annotated[str | None, Header(alias=core_etag.IF_MATCH_HEADER)] = None,
) -> gears_schema.GearRead:
    """Update one of the authenticated user's gears.

    Applies a partial update: omit a field to leave it untouched and send an explicit
    null to clear a nullable one (`brand`, `model`, `purchase_value`).

    Send ``If-Match`` with the gear's ``version`` as an ETag to make the write
    conditional; a stale tag is refused with 412.
    """
    updated = gears_service.edit_gear(gear_id, gear, token_user_id, db, if_match=if_match)
    response.headers["ETag"] = core_etag.format_etag(updated.version)
    return updated


@router.delete(
    "/{gear_id}",
    response_model=None,
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Security(auth_dependencies.check_scopes, scopes=["gears:write"])],
)
@core_rate_limit.limiter.limit(core_rate_limit.WRITE)
def delete_gear(
    request: Request,
    gear_id: core_dependencies.PositiveId,
    token_user_id: auth_dependencies.CurrentUserId,
    db: core_dependencies.DbSession,
) -> None:
    """Delete one of the authenticated user's gears."""
    gears_service.delete_gear(gear_id, token_user_id, db)
