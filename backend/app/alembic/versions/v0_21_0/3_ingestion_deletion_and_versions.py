"""Ingestion retry, account deletion marker and further row versions

The steps run in this order.

Drop the stored Strava OAuth state
----------------------------------

The one-time state that ties a Strava OAuth callback to its user now lives in the platform's
shared state with a short lifetime, so the column and whatever a link in progress left in it
are no longer used.

Let an ingestion refresh wait for a provider's rate limit
---------------------------------------------------------

A refresh that hits a provider's rate limit is now deferred until the limit clears instead of
failing, so its job row records when it runs again.

Record that an account is queued for deletion
---------------------------------------------

An account deletion is a background job, and a job that failed for good or whose in-process worker was
lost leaves the account deactivated with nothing saying it is meant to go. ``deletion_requested_at``
marks it, so a sweep can queue the deletion again, and ``deletion_attempts`` caps how often it does.

Register the local plain-storage data migration
-----------------------------------------------

Add an optimistic-concurrency version to identity providers
-----------------------------------------------------------

Adds a version counter so an identity-provider edit is refused when another admin
has changed the provider since the editor loaded it. Existing rows start at 1.

One goal per user, interval, activity type and goal type
--------------------------------------------------------

A user has one goal for each combination of interval, activity type and goal type. The rule was a
read before the insert, so two concurrent requests could both create the goal, and an edit could change
a goal into another one without the check running. The guarantee moves into the database.

Existing duplicates are removed first, keeping the newest goal (highest id) of each combination. A goal
holds only its own targets, so nothing else points at it.

``ADD CONSTRAINT ... UNIQUE`` is not concurrent, so it blocks writes to the table while it builds. A
user has a handful of goals, so that is brief.

Add an optimistic-concurrency version to user integrations
----------------------------------------------------------

Adds a version counter so a change to a user's Strava client credentials is refused when another request
has changed the row since the client read it. Existing rows start at 1.

Revision ID: 7e2c5a9f4b18
Revises: a8d3e5c1f7b2
Create Date: 2026-11-16 00:00:00.000000

"""

from collections.abc import Sequence
import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "7e2c5a9f4b18"
down_revision: str | None = "a8d3e5c1f7b2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade_drop_strava_state() -> None:
    """Drop the stored OAuth state."""
    op.drop_column("users_integrations", "strava_state")


def downgrade_drop_strava_state() -> None:
    """Restore the empty OAuth state column."""
    op.add_column(
        "users_integrations",
        sa.Column(
            "strava_state",
            sa.String(length=45),
            nullable=True,
            comment="Strava temporary state for link process",
        ),
    )


def upgrade_ingestion_job_retry_after() -> None:
    """Add the instant a deferred refresh runs again."""
    op.add_column(
        "activity_ingestion_jobs",
        sa.Column(
            "retry_after",
            sa.DateTime(timezone=True),
            nullable=True,
            comment="When a deferred refresh runs again; a provider's rate limit clears then",
        ),
    )
    op.alter_column(
        "activity_ingestion_jobs",
        "status",
        existing_type=sa.String(length=20),
        existing_nullable=False,
        existing_server_default="pending",
        comment="pending | processing | deferred | completed | failed",
    )


def downgrade_ingestion_job_retry_after() -> None:
    """Fail the deferred refreshes and drop the column.

    A deferred refresh has no meaning without the column, so each becomes failed rather than
    stuck waiting for a sweep that no longer exists.
    """
    op.execute(
        "UPDATE activity_ingestion_jobs SET status = 'failed', error_code = 'provider_unavailable', "
        "completed_at = now(), updated_at = now() WHERE status = 'deferred'"
    )
    op.alter_column(
        "activity_ingestion_jobs",
        "status",
        existing_type=sa.String(length=20),
        existing_nullable=False,
        existing_server_default="pending",
        comment="pending | processing | completed | failed",
    )
    op.drop_column("activity_ingestion_jobs", "retry_after")


def upgrade_users_deletion_marker() -> None:
    """Add the deletion marker and the attempt counter."""
    op.add_column(
        "users",
        sa.Column(
            "deletion_requested_at",
            sa.DateTime(timezone=True),
            nullable=True,
            comment="When the account was queued for deletion; null for an account that is not being deleted",
        ),
    )
    op.add_column(
        "users",
        sa.Column(
            "deletion_attempts",
            sa.Integer(),
            server_default=sa.text("0"),
            nullable=False,
            comment="How many times the sweep queued this account's deletion again",
        ),
    )


def downgrade_users_deletion_marker() -> None:
    """Drop the deletion marker and the attempt counter."""
    op.drop_column("users", "deletion_attempts")
    op.drop_column("users", "deletion_requested_at")


def upgrade_register_local_plain_storage() -> None:
    """Register the local plain-storage data migration."""
    op.execute(
        """
    INSERT INTO migrations (id, name, description, executed) VALUES
    (11, 'v0.21.0', 'Move local storage objects into plain area paths', false);
    """
    )


def downgrade_register_local_plain_storage() -> None:
    """Remove the migration registration."""
    op.execute("DELETE FROM migrations WHERE id = 11;")


def upgrade_identity_providers_version() -> None:
    """Add the version column to identity providers."""
    op.add_column(
        "identity_providers",
        sa.Column(
            "version",
            sa.Integer(),
            server_default=sa.text("1"),
            nullable=False,
            comment="Optimistic-concurrency counter, surfaced to clients as the ETag",
        ),
    )


def downgrade_identity_providers_version() -> None:
    """Drop the identity-provider version column."""
    op.drop_column("identity_providers", "version")


_KEEP_NEWEST = (
    "DELETE FROM users_goals WHERE id NOT IN "
    "(SELECT max(id) FROM users_goals GROUP BY user_id, interval, activity_type, goal_type)"
)


def upgrade_users_goals_one_per_scope() -> None:
    op.execute(_KEEP_NEWEST)
    op.create_unique_constraint(
        "uq_users_goals_user_scope", "users_goals", ["user_id", "interval", "activity_type", "goal_type"]
    )


def downgrade_users_goals_one_per_scope() -> None:
    op.drop_constraint("uq_users_goals_user_scope", "users_goals", type_="unique")


def upgrade_users_integrations_version() -> None:
    """Add the version column to user integrations."""
    op.add_column(
        "users_integrations",
        sa.Column(
            "version",
            sa.Integer(),
            server_default=sa.text("1"),
            nullable=False,
            comment="Optimistic-concurrency counter, surfaced to clients as the ETag",
        ),
    )


def downgrade_users_integrations_version() -> None:
    """Drop the user-integrations version column."""
    op.drop_column("users_integrations", "version")


def upgrade() -> None:
    """Run every step in order."""
    upgrade_drop_strava_state()
    upgrade_ingestion_job_retry_after()
    upgrade_users_deletion_marker()
    upgrade_register_local_plain_storage()
    upgrade_identity_providers_version()
    upgrade_users_goals_one_per_scope()
    upgrade_users_integrations_version()


def downgrade() -> None:
    """Undo every step, last first."""
    downgrade_users_integrations_version()
    downgrade_users_goals_one_per_scope()
    downgrade_identity_providers_version()
    downgrade_register_local_plain_storage()
    downgrade_users_deletion_marker()
    downgrade_ingestion_job_retry_after()
    downgrade_drop_strava_state()
