"""Shared progressive lockout state for sensitive account operations."""

from datetime import datetime
from typing import Protocol, runtime_checkable

from jasil.providers import StateProvider

import core.dependencies as core_dependencies
import modules.auth.lockout.contracts as lockout_contracts
import modules.auth.lockout.integration_service as lockout_integration


@runtime_checkable
class StepUpStore(Protocol):
    """Contract for user-keyed step-up attempt state."""

    def is_locked_out(self, key: str) -> bool: ...

    def get_lockout_time(self, key: str) -> datetime | None: ...

    def record_failed_attempt(self, key: str) -> int: ...

    def reset_attempts(self, key: str) -> None: ...

    def clear_all(self) -> None: ...


class StepUpAttempts:
    """Track step-up failures with the configured progressive lockout tiers."""

    def __init__(self, state: StateProvider) -> None:
        """Bind this store to the request's platform state provider."""
        self._lockout = lockout_integration.new_progressive_lockout(
            state,
            name="step_up",
            display_name="Step-up",
            tiers=lockout_contracts.STEP_UP_LOCKOUT_TIERS,
            attempts_ttl_seconds=2 * 60 * 60,
        )

    def is_locked_out(self, key: str) -> bool:
        return self._lockout.is_locked_out(key)

    def get_lockout_time(self, key: str) -> datetime | None:
        return self._lockout.get_lockout_time(key)

    def record_failed_attempt(self, key: str) -> int:
        return self._lockout.record_failed_attempt(key)

    def reset_attempts(self, key: str) -> None:
        self._lockout.reset_attempts(key)

    def clear_all(self) -> None:
        self._lockout.clear_all()


def get_step_up_attempts(state: core_dependencies.PlatformState) -> StepUpStore:
    """Create a step-up store over the shared platform state provider."""
    return StepUpAttempts(state)
