"""FastAPI providers for the onboarding setup-token store."""

from typing import Annotated

from fastapi import Depends

import core.dependencies as core_dependencies
import modules.auth.onboarding.token_store as onboarding_token_store


def get_onboarding_token_store(state: core_dependencies.PlatformState) -> onboarding_token_store.OnboardingTokenStore:
    """Build the setup-token store from the active platform state provider."""
    return onboarding_token_store.OnboardingTokenStore(state)


#: The setup-token store bound to the active platform state provider.
OnboardingTokens = Annotated[onboarding_token_store.OnboardingTokenStore, Depends(get_onboarding_token_store)]
