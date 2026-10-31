"""Startup work for first-run onboarding."""

import jasil.runtime as platform_runtime

import core.database as core_database
import core.logger as core_logger
import modules.auth.onboarding.token_store as onboarding_token_store
import modules.users.users.integration_service as users_integration

logger = core_logger.get_logger(__name__)


def issue_onboarding_token_if_needed() -> None:
    """Mint a setup token and tell the operator, while no account exists.

    Every web worker mints its own token and all of them are valid; only one onboarding can succeed, because the
    zero-user check runs again under a lock when the account is created. Nothing happens once an account exists.
    """
    with core_database.SessionLocal() as db:
        onboarding_required = not users_integration.any_user_exists(db)
    if not onboarding_required:
        return
    token = onboarding_token_store.OnboardingTokenStore(platform_runtime.get_state()).issue()
    logger.warning(
        "First-run onboarding required: no account exists yet. Open Endurain in a browser and enter the setup token",
        extra=core_logger.context(console=True, setup_token=token),
    )
