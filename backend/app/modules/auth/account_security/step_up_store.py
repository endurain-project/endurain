"""Shared state for sensitive account operations: progressive lockout, TOTP replay and step-up tickets."""

from datetime import datetime
from typing import Protocol, runtime_checkable

from jasil.providers import StateProvider

import core.dependencies as core_dependencies
import modules.auth.identity_providers.contracts as identity_providers_contracts
import modules.auth.identity_providers.integration_service as identity_providers_integration
import modules.auth.lockout.contracts as lockout_contracts
import modules.auth.lockout.integration_service as lockout_integration
import modules.auth.mfa.integration_service as mfa_integration


@runtime_checkable
class StepUpStore(Protocol):
    """Contract for user-keyed step-up attempt state."""

    def is_locked_out(self, key: str) -> bool:
        """Return whether the supplied key is currently locked out."""
        ...

    def get_lockout_time(self, key: str) -> datetime | None:
        """Return the active lockout expiry, if one exists."""
        ...

    def record_failed_attempt(self, key: str) -> int:
        """Record a failed attempt and return the updated count."""
        ...

    def reset_attempts(self, key: str) -> None:
        """Clear the failed-attempt count for the supplied key."""
        ...

    def clear_all(self) -> None:
        """Clear all tracked lockout attempts."""
        ...

    def claim_totp_step(self, user_id: int, step: int) -> bool:
        """Record an accepted TOTP step as used; False when it already was."""
        ...

    def read_ticket(self, ticket: str) -> identity_providers_contracts.StepUpTicket | None:
        """Return an identity-provider step-up ticket without redeeming it."""
        ...

    def redeem_ticket(self, ticket: str) -> identity_providers_contracts.StepUpTicket | None:
        """Redeem an identity-provider step-up ticket atomically."""
        ...


class StepUpAttempts:
    """Track step-up failures with the configured progressive lockout tiers."""

    def __init__(self, state: StateProvider) -> None:
        """Bind this store to the request's platform state provider."""
        self._state = state
        self._lockout = lockout_integration.new_progressive_lockout(
            state,
            name="step_up",
            tiers=lockout_contracts.STEP_UP_LOCKOUT_TIERS,
            attempts_ttl_seconds=2 * 60 * 60,
        )

    def is_locked_out(self, key: str) -> bool:
        """Return whether the supplied key is locked out."""
        return self._lockout.is_locked_out(key)

    def get_lockout_time(self, key: str) -> datetime | None:
        """Return the active lockout expiry, if one exists."""
        return self._lockout.get_lockout_time(key)

    def record_failed_attempt(self, key: str) -> int:
        """Record a failed attempt and return the updated count."""
        return self._lockout.record_failed_attempt(key)

    def reset_attempts(self, key: str) -> None:
        """Clear the failed-attempt count for the supplied key."""
        self._lockout.reset_attempts(key)

    def clear_all(self) -> None:
        """Clear all tracked lockout attempts."""
        self._lockout.clear_all()

    def claim_totp_step(self, user_id: int, step: int) -> bool:
        """Record an accepted TOTP step as used; False when it already was."""
        return mfa_integration.claim_totp_step(self._state, user_id, step)

    def read_ticket(self, ticket: str) -> identity_providers_contracts.StepUpTicket | None:
        """Return an identity-provider step-up ticket without redeeming it."""
        return identity_providers_integration.read_step_up_ticket(self._state, ticket)

    def redeem_ticket(self, ticket: str) -> identity_providers_contracts.StepUpTicket | None:
        """Redeem an identity-provider step-up ticket atomically."""
        return identity_providers_integration.redeem_step_up_ticket(self._state, ticket)


def get_step_up_attempts(state: core_dependencies.PlatformState) -> StepUpStore:
    """Create a step-up store over the shared platform state provider."""
    return StepUpAttempts(state)
