"""1: add users streak settings table

Revision ID: 7c1e5a9d3b42
Revises: d54bdd779392
Create Date: 2026-10-13 20:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "7c1e5a9d3b42"
down_revision: str | None = "d54bdd779392"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create the users_streak_settings table and its unique user_id index."""
    op.create_table(
        "users_streak_settings",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column(
            "user_id",
            sa.Integer(),
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
