"""Unauthenticated password-reset endpoints."""

from fastapi import APIRouter, Request

import core.dependencies as core_dependencies
import core.rate_limit as core_rate_limit
import modules.auth.password_reset_tokens.schema as password_reset_schema
import modules.auth.password_reset_tokens.service as password_reset_service

router = APIRouter()


@router.post(
    "/password-reset/request",
    response_model=password_reset_schema.PasswordResetRead,
)
@core_rate_limit.limiter.limit(core_rate_limit.SENSITIVE)
def request_password_reset(
    request: Request,
    request_data: password_reset_schema.PasswordResetRequest,
    state: core_dependencies.PlatformState,
    db: core_dependencies.DbSession,
) -> password_reset_schema.PasswordResetRead:
    """Request a password reset without revealing whether the email exists."""
    password_reset_service.request_password_reset_email(request_data.email, state, db)
    return password_reset_schema.PasswordResetRead(
        message="If the email exists in the system, a password reset link has been sent."
    )


@router.post(
    "/password-reset/confirm",
    response_model=password_reset_schema.PasswordResetRead,
)
@core_rate_limit.limiter.limit(core_rate_limit.SENSITIVE)
def confirm_password_reset(
    request: Request,
    confirm_data: password_reset_schema.PasswordResetConfirm,
    db: core_dependencies.DbSession,
) -> password_reset_schema.PasswordResetRead:
    """Confirm a password reset using a token and replacement password."""
    password_reset_service.use_password_reset_token(confirm_data.token, confirm_data.new_password, db)
    return password_reset_schema.PasswordResetRead(message="Password reset successful")
