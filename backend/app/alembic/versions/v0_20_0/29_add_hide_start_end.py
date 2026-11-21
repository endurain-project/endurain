"""29: add the hide-route-start-and-end privacy flags

Revision ID: 2b8e5d1f7c46
Revises: c91ac2dad0f0
Create Date: 2026-11-13 00:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "2b8e5d1f7c46"
down_revision: str | None = "c91ac2dad0f0"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add the per-activity flag and the user default, both off."""
    op.add_column(
        "activities",
        sa.Column(
            "hide_start_end",
            sa.Boolean(),
            nullable=False,
            server_default="false",
            comment="Hide activity route start and end",
        ),
    )
    op.add_column(
        "users_privacy_settings",
        sa.Column(
            "hide_activity_start_end",
            sa.Boolean(),
            nullable=False,
            server_default="false",
            comment="Hide activity route start and end",
        ),
    )


def downgrade() -> None:
    """Remove both flags."""
    op.drop_column("users_privacy_settings", "hide_activity_start_end")
    op.drop_column("activities", "hide_start_end")
