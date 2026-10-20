"""Gear API router endpoints."""

from collections.abc import Callable
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request, Security, status
from sqlalchemy.orm import Session

import core.database as core_database
import core.dependencies as core_dependencies
import core.pagination as core_pagination
import core.rate_limit as core_rate_limit
import modules.auth.dependencies as auth_dependencies
import modules.gears.gear.dependencies as gears_dependencies
import modules.gears.gear.schema as gears_schema
import modules.gears.gear.service as gears_service

router = APIRouter()


@router.get(
    "",
    response_model=gears_schema.GearsListResponse,
)
def read_gears_user_all_pagination(
    _check_scopes: Annotated[Callable, Security(auth_dependencies.check_scopes, scopes=["gears:read"])],
    token_user_id: Annotated[int, Depends(auth_dependencies.get_sub_from_access_token)],
    db: Annotated[Session, Depends(core_database.get_db)],
    page: Annotated[core_pagination.PageParams, Depends(core_pagination.list_page_params)],
    show_inactive: Annotated[bool | None, Query(description="Filter by inactive status")] = None,
) -> gears_schema.GearsListResponse:
    """Retrieve one page of the authenticated user's gears, with the matching total."""
    return gears_service.list_gears(
        token_user_id,
        db,
        page_number=page.page_number,
        num_records=page.num_records,
        show_inactive=show_inactive,
    )


@router.get(
    "/id/{gear_id}",
    response_model=gears_schema.GearDetailRead,
)
def read_gear_id(
    gear_id: core_dependencies.PositiveId,
    _check_scopes: Annotated[Callable, Security(auth_dependencies.check_scopes, scopes=["gears:read"])],
    token_user_id: Annotated[int, Depends(auth_dependencies.get_sub_from_access_token)],
    db: Annotated[Session, Depends(core_database.get_db)],
) -> gears_schema.GearDetailRead:
    """Retrieve a gear by ID with its total distance, time and components cost."""
    return gears_service.read_gear_detail(gear_id, token_user_id, db)


@router.get(
    "/nickname/contains/{nickname}",
    response_model=list[gears_schema.GearRead],
)
def read_gear_user_contains_nickname(
    nickname: gears_dependencies.GearNickname,
    _check_scopes: Annotated[Callable, Security(auth_dependencies.check_scopes, scopes=["gears:read"])],
    token_user_id: Annotated[int, Depends(auth_dependencies.get_sub_from_access_token)],
    db: Annotated[Session, Depends(core_database.get_db)],
) -> list[gears_schema.GearRead]:
    """Retrieve up to 200 of the authenticated user's gears whose nickname contains the text."""
    return gears_service.list_gears_containing_nickname(token_user_id, nickname, db)


@router.get(
    "/nickname/{nickname}",
    response_model=gears_schema.GearRead,
)
def read_gear_user_by_nickname(
    nickname: gears_dependencies.GearNickname,
    _check_scopes: Annotated[Callable, Security(auth_dependencies.check_scopes, scopes=["gears:read"])],
    token_user_id: Annotated[int, Depends(auth_dependencies.get_sub_from_access_token)],
    db: Annotated[Session, Depends(core_database.get_db)],
) -> gears_schema.GearRead:
    """Retrieve the authenticated user's gear by exact nickname."""
    return gears_service.read_gear_by_nickname(token_user_id, nickname, db)


@router.get(
    "/type/{gear_type}",
    response_model=list[gears_schema.GearRead],
)
def read_gear_user_by_type(
    gear_type: gears_schema.GearType,
    _check_scopes: Annotated[Callable, Security(auth_dependencies.check_scopes, scopes=["gears:read"])],
    token_user_id: Annotated[int, Depends(auth_dependencies.get_sub_from_access_token)],
    db: Annotated[Session, Depends(core_database.get_db)],
) -> list[gears_schema.GearRead]:
    """Retrieve up to 200 of the authenticated user's gears of one type."""
    return gears_service.list_gears_by_type(token_user_id, gear_type, db)


@router.post(
    "",
    response_model=gears_schema.GearRead,
    status_code=status.HTTP_201_CREATED,
)
@core_rate_limit.limiter.limit(core_rate_limit.WRITE)
def create_gear(
    request: Request,
    gear: gears_schema.GearCreateRequest,
    _check_scopes: Annotated[Callable, Security(auth_dependencies.check_scopes, scopes=["gears:write"])],
    token_user_id: Annotated[int, Depends(auth_dependencies.get_sub_from_access_token)],
    db: Annotated[Session, Depends(core_database.get_db)],
) -> gears_schema.GearRead:
    """Create a gear for the authenticated user."""
    return gears_service.create_gear(gear, token_user_id, db)


@router.put(
    "",
    response_model=gears_schema.GearRead,
)
@core_rate_limit.limiter.limit(core_rate_limit.WRITE)
def edit_gear(
    request: Request,
    gear: gears_schema.GearUpdate,
    _check_scopes: Annotated[Callable, Security(auth_dependencies.check_scopes, scopes=["gears:write"])],
    token_user_id: Annotated[int, Depends(auth_dependencies.get_sub_from_access_token)],
    db: Annotated[Session, Depends(core_database.get_db)],
) -> gears_schema.GearRead:
    """Update one of the authenticated user's gears."""
    return gears_service.edit_gear(gear, token_user_id, db)


@router.delete(
    "/{gear_id}",
    response_model=None,
    status_code=status.HTTP_204_NO_CONTENT,
)
@core_rate_limit.limiter.limit(core_rate_limit.WRITE)
def delete_gear(
    request: Request,
    gear_id: core_dependencies.PositiveId,
    _check_scopes: Annotated[Callable, Security(auth_dependencies.check_scopes, scopes=["gears:write"])],
    token_user_id: Annotated[int, Depends(auth_dependencies.get_sub_from_access_token)],
    db: Annotated[Session, Depends(core_database.get_db)],
) -> None:
    """Delete one of the authenticated user's gears."""
    gears_service.delete_gear(gear_id, token_user_id, db)
