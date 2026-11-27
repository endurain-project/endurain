"""96: users get weekly streak settings

Create ``users_streak_settings``, which holds at most one row per user: how many activities a week needs to keep
the weekly streak, which activity types count, and whether the streak is shown on the user's profile. A user
without a row gets the defaults, so existing users need no data migration.

The downgrade drops the table.

Revision ID: 4b8d2f6a9c13
Revises: e95a7c1d4b36
Create Date: 2026-11-27 00:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "4b8d2f6a9c13"
down_revision: str | None = "e95a7c1d4b36"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create the users_streak_settings table and its unique user_id index."""
    op.create_table(
        "users_streak_settings",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "user_id",
            sa.Uuid(),
            nullable=False,
            comment="User ID that the streak settings belong to",
        ),
        sa.Column(
            "min_activities_per_week",
            sa.Integer(),
            nullable=False,
            server_default="1",
            comment="Activities needed in a week to keep the streak",
        ),
        sa.Column(
            "activity_types",
            sa.JSON(),
            nullable=True,
            comment="Activity type IDs counted for the streak (null = all)",
        ),
        sa.Column(
            "show_on_profile",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
            comment="Show the streak to other users on the profile",
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_users_streak_settings_user_id"),
        "users_streak_settings",
        ["user_id"],
        unique=True,
    )


def downgrade() -> None:
    """Drop the users_streak_settings table and its index."""
    op.drop_index(op.f("ix_users_streak_settings_user_id"), table_name="users_streak_settings")
    op.drop_table("users_streak_settings")
