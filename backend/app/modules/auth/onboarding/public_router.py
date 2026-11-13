"""Unauthenticated first-run onboarding endpoints."""

from fastapi import APIRouter, Request, Response, status

import core.dependencies as core_dependencies
import core.etag as core_etag
import core.openapi_contract as core_openapi_contract
import core.rate_limit as core_rate_limit
import modules.auth.onboarding.dependencies as onboarding_dependencies
import modules.auth.onboarding.schema as onboarding_schema
import modules.auth.onboarding.service as onboarding_service
import modules.users.users.schema as users_schema

router = APIRouter()


@router.get("", response_model=onboarding_schema.OnboardingStatusRead)
@core_rate_limit.limiter.limit(core_rate_limit.PUBLIC_READ)
def read_onboarding_status(
    request: Request,
    db: core_dependencies.DbSession,
) -> onboarding_schema.OnboardingStatusRead:
    """Tell whether the installation has no account yet and needs its first administrator."""
    return onboarding_service.get_onboarding_status(db)


@router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    response_model=users_schema.UserRead,
    responses={
        201: {"headers": core_openapi_contract.ETAG_HEADERS},
        400: {"description": "The setup token is unknown, expired or already used."},
    },
)
@core_rate_limit.limiter.limit(core_rate_limit.SENSITIVE)
def complete_onboarding(
    request: Request,
    onboarding: onboarding_schema.OnboardingCreate,
    store: onboarding_dependencies.OnboardingTokens,
    db: core_dependencies.DbSession,
    response: Response,
) -> users_schema.UserRead:
    """Create the first administrator with the setup token printed in the server log."""
    created = onboarding_service.complete_onboarding(onboarding, store, db)
    core_etag.set_etag(response, created.version)
    return created
