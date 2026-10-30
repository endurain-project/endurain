"""Unauthenticated first-run onboarding endpoints."""

from fastapi import APIRouter, Request, status

import core.dependencies as core_dependencies
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


@router.post("", status_code=status.HTTP_201_CREATED, response_model=users_schema.UsersRead)
@core_rate_limit.limiter.limit(core_rate_limit.SENSITIVE)
def complete_onboarding(
    request: Request,
    onboarding: onboarding_schema.OnboardingCreate,
    store: onboarding_dependencies.OnboardingTokens,
    db: core_dependencies.DbSession,
) -> users_schema.UsersRead:
    """Create the first administrator with the setup token printed in the server log."""
    return onboarding_service.complete_onboarding(onboarding, store, db)
