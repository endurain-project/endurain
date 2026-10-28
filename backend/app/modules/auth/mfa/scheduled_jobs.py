"""MFA maintenance jobs."""

import core.dependencies as core_dependencies
import core.scheduler as core_scheduler
import modules.auth.mfa.pending_login_store as pending_login_store


def cleanup_expired_pending_mfa_logins() -> int:
    """Run the pending-MFA cleanup entrypoint; pending entries expire through the provider TTL."""
    return pending_login_store.cleanup_expired_pending_mfa_logins(core_dependencies.get_platform_state())


def recurring_jobs() -> tuple[core_scheduler.ScheduledJob, ...]:
    """Return the recurring jobs owned by MFA."""
    return (
        core_scheduler.ScheduledJob(
            cleanup_expired_pending_mfa_logins,
            5,
            "evict expired pending MFA login entries",
        ),
    )
