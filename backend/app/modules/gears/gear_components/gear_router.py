"""Gear components API router endpoints for one gear, served under ``/gears``."""

from fastapi import APIRouter, Security

import core.dependencies as core_dependencies
import core.pagination as core_pagination
import modules.auth.dependencies as auth_dependencies
import modules.gears.gear_components.schema as gear_components_schema
import modules.gears.gear_components.service as gear_components_service

router = APIRouter()


@router.get(
    "/{gear_id}/components",
    response_model=core_pagination.Page[gear_components_schema.GearComponentRead],
    dependencies=[Security(auth_dependencies.check_scopes, scopes=["gears:read"])],
)
def read_gear_components_gear_id(
    gear_id: core_dependencies.PositiveId,
    token_user_id: auth_dependencies.CurrentUserId,
    db: core_dependencies.DbSession,
    page: core_pagination.ChildPage,
    active: bool | None = None,
) -> core_pagination.Page[gear_components_schema.GearComponentRead]:
    """Retrieve one page of a gear's components with the distance and time each has accumulated."""
    return gear_components_service.list_components_for_gear(
        gear_id, token_user_id, db, active=active, page_number=page.page_number, num_records=page.num_records
    )
