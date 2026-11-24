"""Correct the speed column comments

The ``activities.average_speed`` and ``activities.max_speed`` comments gave the unit as seconds per meter, but the
columns hold meters per second. Only the comments change; no data does.

The downgrade restores the previous comments.

Revision ID: 86ddd2645a0c
Revises: 3c9e5a7d1f20
Create Date: 2026-11-24 00:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "86ddd2645a0c"
down_revision: str | None = "3c9e5a7d1f20"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Comment ``average_speed`` and ``max_speed`` as meters per second."""
    op.alter_column(
        "activities",
        "average_speed",
        existing_type=sa.DECIMAL(precision=20, scale=10),
        existing_nullable=True,
        comment="Average speed in meters per second (m/s)",
        existing_comment="Average speed seconds per meter (s/m)",
    )
    op.alter_column(
        "activities",
        "max_speed",
        existing_type=sa.DECIMAL(precision=20, scale=10),
        existing_nullable=True,
        comment="Max speed in meters per second (m/s)",
        existing_comment="Max speed seconds per meter (s/m)",
    )


def downgrade() -> None:
    """Restore the seconds per meter comments on ``average_speed`` and ``max_speed``."""
    op.alter_column(
        "activities",
        "average_speed",
        existing_type=sa.DECIMAL(precision=20, scale=10),
        existing_nullable=True,
        comment="Average speed seconds per meter (s/m)",
        existing_comment="Average speed in meters per second (m/s)",
    )
    op.alter_column(
        "activities",
        "max_speed",
        existing_type=sa.DECIMAL(precision=20, scale=10),
        existing_nullable=True,
        comment="Max speed seconds per meter (s/m)",
        existing_comment="Max speed in meters per second (m/s)",
    )
