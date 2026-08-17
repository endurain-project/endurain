"""The auth module's scheduled work, declared by the module that owns it.

The callables all come from :mod:`modules.auth.maintenance`, which is auth's
single maintenance surface; this file only says how often each runs, so the
composition root can collect it alongside every other module's declaration.
"""

import core.scheduler as core_scheduler
import modules.auth.maintenance as auth_maintenance


def recurring_jobs() -> tuple[core_scheduler.ScheduledJob, ...]:
    """
    Return the auth module's recurring scheduled jobs.

    Args:
        None.

    Returns:
        The module's scheduled jobs, for the composition root to register.

    Raises:
        None.
    """
    return (
        core_scheduler.ScheduledJob(
            auth_maintenance.delete_invalid_password_reset_tokens_from_db,
            60,
            "delete invalid password reset tokens from the database",
        ),
        core_scheduler.ScheduledJob(
            auth_maintenance.delete_invalid_sign_up_tokens_from_db,
            60,
            "delete invalid sign-up tokens from the database",
        ),
        core_scheduler.ScheduledJob(
            auth_maintenance.delete_expired_oauth_states_from_db,
            5,
            "delete expired OAuth states from the database",
        ),
        core_scheduler.ScheduledJob(
            auth_maintenance.delete_idp_link_expired_tokens_from_db,
            5,
            "delete expired IdP link tokens from the database",
        ),
        core_scheduler.ScheduledJob(
            auth_maintenance.cleanup_idle_sessions,
            15,
            "delete expired sessions from the database",
        ),
        core_scheduler.ScheduledJob(
            auth_maintenance.cleanup_expired_rotated_tokens,
            1,
            "delete expired rotated tokens from the database",
        ),
        core_scheduler.ScheduledJob(
            auth_maintenance.cleanup_expired_pending_mfa_logins,
            5,
            "evict expired pending MFA login entries",
        ),
    )
