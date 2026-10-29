"""Unauthenticated sign-up and email-verification endpoints."""

from fastapi import APIRouter, Request, status

import core.dependencies as core_dependencies
import core.rate_limit as core_rate_limit
import modules.auth.sign_up_tokens.schema as sign_up_schema
import modules.auth.sign_up_tokens.service as sign_up_service
import modules.users.users.schema as users_schema

router = APIRouter()


@router.post(
    "/sign-up/request",
    status_code=status.HTTP_201_CREATED,
    response_model=sign_up_schema.SignUpRead,
)
@core_rate_limit.limiter.limit(core_rate_limit.SENSITIVE)
def signup(
    request: Request,
    user: users_schema.UsersSignup,
    state: core_dependencies.PlatformState,
    db: core_dependencies.DbSession,
) -> sign_up_schema.SignUpRead:
    """Create an account using the configured sign-up policy."""
    return sign_up_service.signup(user, state, db)


@router.post(
    "/sign-up/confirm",
    response_model=sign_up_schema.SignUpRead,
)
@core_rate_limit.limiter.limit(core_rate_limit.SENSITIVE)
def verify_email(
    request: Request,
    confirm_data: sign_up_schema.SignUpConfirm,
    db: core_dependencies.DbSession,
) -> sign_up_schema.SignUpRead:
    """Verify an account's email address using its one-time token."""
    return sign_up_service.verify_email(confirm_data.token, db)
