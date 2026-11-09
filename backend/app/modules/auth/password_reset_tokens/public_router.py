"""Unauthenticated password-reset endpoints."""

from fastapi import APIRouter, Request, status

import core.dependencies as core_dependencies
import core.network as core_network
import core.rate_limit as core_rate_limit
import modules.auth.password_reset_tokens.schema as password_reset_schema
import modules.auth.password_reset_tokens.service as password_reset_service

router = APIRouter()


@router.post(
    "/password-reset/request",
    response_model=None,
    status_code=status.HTTP_204_NO_CONTENT,
)
@core_rate_limit.limiter.limit(core_rate_limit.SENSITIVE)
def request_password_reset(
    request: Request,
    request_data: password_reset_schema.PasswordResetRequest,
    db: core_dependencies.DbSession,
) -> None:
    """Request a password reset without revealing whether the email exists."""
    password_reset_service.request_password_reset_email(
        request_data.email, core_network.get_ip_address(request), core_network.get_user_agent(request), db
    )


@router.post(
    "/password-reset/confirm",
    response_model=None,
    status_code=status.HTTP_204_NO_CONTENT,
)
@core_rate_limit.limiter.limit(core_rate_limit.SENSITIVE)
def confirm_password_reset(
    request: Request,
    confirm_data: password_reset_schema.PasswordResetConfirm,
    db: core_dependencies.DbSession,
) -> None:
    """Confirm a password reset using a token and replacement password."""
    password_reset_service.use_password_reset_token(confirm_data.token, confirm_data.password, db)


@router.post(
    "/password-reset/validate",
    response_model=None,
    status_code=status.HTTP_204_NO_CONTENT,
)
@core_rate_limit.limiter.limit(core_rate_limit.SENSITIVE)
def validate_password_reset_token(
    request: Request,
    validate_data: password_reset_schema.PasswordResetValidate,
    db: core_dependencies.DbSession,
) -> None:
    """Answer 204 when a reset token is still usable, else the same 400 as the confirm route.

    Sent as a body so the token stays out of URLs and logs. Does not consume the token.
    """
    password_reset_service.validate_password_reset_token(validate_data.token, db)
