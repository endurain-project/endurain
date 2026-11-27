"""Add the start point of an activity

``activities.start_latitude`` and ``activities.start_longitude`` hold where an activity starts: the first recorded
position of its samples, or for a multisport activity the start point of its first leg that has one. Both are NULL for
an activity with no position, and for every row that existed before this revision, which a later data migration fills.

The downgrade drops both columns.

Revision ID: 5b8e2d4f6a13
Revises: 3c1f5a7d9e24
Create Date: 2026-11-27 00:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "5b8e2d4f6a13"
down_revision: str | None = "3c1f5a7d9e24"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add the nullable ``start_latitude`` and ``start_longitude`` columns."""
    op.add_column(
        "activities",
        sa.Column(
            "start_latitude",
            postgresql.DOUBLE_PRECISION(),
            nullable=True,
            comment="Latitude of the activity's start point, in degrees; NULL when the activity has no position",
        ),
    )
    op.add_column(
        "activities",
        sa.Column(
            "start_longitude",
            postgresql.DOUBLE_PRECISION(),
            nullable=True,
            comment="Longitude of the activity's start point, in degrees; NULL when the activity has no position",
        ),
    )


def downgrade() -> None:
    """Drop ``start_latitude`` and ``start_longitude``."""
    op.drop_column("activities", "start_longitude")
    op.drop_column("activities", "start_latitude")
