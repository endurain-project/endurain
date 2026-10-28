"""Unauthenticated sign-up and email-verification endpoints."""

from typing import Annotated

from fastapi import APIRouter, Depends, Request

import core.dependencies as core_dependencies
import core.rate_limit as core_rate_limit
import modules.auth.identity_service as auth_identity_service
import modules.auth.sign_up_tokens.schema as sign_up_schema
import modules.auth.sign_up_tokens.service as sign_up_service
import modules.users.users.schema as users_schema

router = APIRouter()


@router.post(
    "/sign-up/request",
    status_code=201,
    response_model=sign_up_schema.SignUpResponse,
)
@core_rate_limit.limiter.limit(core_rate_limit.SENSITIVE)
def signup(
    request: Request,
    user: users_schema.UsersSignup,
    identity_service: Annotated[
        auth_identity_service.IdentityService,
        Depends(auth_identity_service.get_identity_service),
    ],
    db: core_dependencies.DbSession,
) -> sign_up_schema.SignUpResponse:
    """Create an account using the configured sign-up policy."""
    return sign_up_service.signup(user, identity_service, db)


@router.post(
    "/sign-up/confirm",
    response_model=sign_up_schema.SignUpResponse,
)
@core_rate_limit.limiter.limit(core_rate_limit.SENSITIVE)
def verify_email(
    request: Request,
    confirm_data: sign_up_schema.SignUpConfirm,
    db: core_dependencies.DbSession,
) -> sign_up_schema.SignUpResponse:
    """Verify an account's email address using its one-time token."""
    return sign_up_service.verify_email(confirm_data.token, db)
