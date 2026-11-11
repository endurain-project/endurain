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

    def get_account_lockout_time(self, user_id: int) -> datetime | None:
        """Return when the account-wide step-up lock ends, if the account is locked."""
        ...

    def record_account_failure(self, user_id: int) -> bool:
        """Count a failed step-up against the account; True when this failure locked the account."""
        ...

    def reset_account(self, user_id: int) -> None:
        """Clear the account-wide failed-step-up count and lock of a user."""
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
    """Track step-up failures per session with progressive lockout tiers, and per account with a far higher cap."""

    def __init__(self, state: StateProvider) -> None:
        """Bind this store to the request's platform state provider."""
        self._state = state
        self._lockout = lockout_integration.new_progressive_lockout(
            state,
            name="step_up",
            tiers=lockout_contracts.STEP_UP_LOCKOUT_TIERS,
            attempts_ttl_seconds=2 * 60 * 60,
        )
        self._by_account = lockout_integration.new_step_up_account_lockout(state)

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

    def get_account_lockout_time(self, user_id: int) -> datetime | None:
        """Return when the account-wide step-up lock ends, if the account is locked."""
        return self._by_account.get_lockout_time(str(user_id))

    def record_account_failure(self, user_id: int) -> bool:
        """Count a failed step-up against the account; True when this failure locked the account."""
        return self._by_account.record_failure(str(user_id)).newly_locked

    def reset_account(self, user_id: int) -> None:
        """Clear the account-wide failed-step-up count and lock of a user."""
        self._by_account.reset_attempts(str(user_id))

    def clear_all(self) -> None:
        """Clear all tracked lockout attempts."""
        self._lockout.clear_all()
        self._by_account.clear_all()

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
