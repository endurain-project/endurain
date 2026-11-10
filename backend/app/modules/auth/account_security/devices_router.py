"""The signed-in user's known-device routes, mounted under ``/profile/devices``."""

from typing import Annotated

from fastapi import APIRouter, Depends, Request, Security, status

import core.dependencies as core_dependencies
import core.pagination as core_pagination
import core.rate_limit as core_rate_limit
import modules.auth.account_security.device_service as device_service
import modules.auth.dependencies as auth_dependencies
import modules.auth.known_devices.dependencies as known_devices_dependencies
import modules.auth.known_devices.schema as known_devices_schema
import modules.auth.schema as auth_schema

router = APIRouter()


@router.get(
    "",
    response_model=known_devices_schema.KnownDevicePage,
    dependencies=[Security(auth_dependencies.check_scopes, scopes=["account:security"])],
)
def list_user_devices(
    token_user_id: auth_dependencies.CurrentUserId,
    device_id: known_devices_dependencies.DeviceId,
    page: core_pagination.ListPage,
    db: core_dependencies.DbSession,
) -> known_devices_schema.KnownDevicePage:
    """List one page of the devices the authenticated user is known to sign in from, latest sign-in first.

    A device is known until a security change of the account or the user forgets it, and a sign-in from an unknown device is announced by email. `current` marks
    the device the request comes from.
    """
    return device_service.list_user_devices(token_user_id, device_id, page, db)


@router.post(
    "/{device_id}/delete",
    status_code=status.HTTP_204_NO_CONTENT,
    response_model=None,
    dependencies=[Security(auth_dependencies.check_scopes, scopes=["account:security"])],
)
@core_rate_limit.limiter.limit(core_rate_limit.SENSITIVE)
def forget_user_device(
    device_id: core_dependencies.PositiveId,
    body: auth_schema.StepUpRequest,
    request: Request,
    token_user_id: auth_dependencies.CurrentUserId,
    token_session_id: auth_dependencies.CurrentSessionId,
    step_up_store: Annotated[
        auth_dependencies.StepUpStore,
        Depends(auth_dependencies.get_step_up_attempts),
    ],
    db: core_dependencies.DbSession,
) -> None:
    """Forget a device after step-up verification, so the next sign-in from it is announced as a new device."""
    device_service.forget_user_device(device_id, token_user_id, token_session_id, body.step_up, step_up_store, db)
