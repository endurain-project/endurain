"""21: add activities.thumbnail_next_attempt_at

Revision ID: c4a7d92e5b18
Revises: 9b4e2f6a1c07
Create Date: 2026-10-15 00:00:00.000000

The thumbnail backfill walks activities with no stored thumbnail. One that has no
GPS track, or whose render keeps failing, stays a candidate forever and costs a
tile-server round trip every pass. Recording when it may be tried again keeps it
out of the passes in between. NULL means "due now", so existing rows need no
backfill.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c4a7d92e5b18"
down_revision: str | None = "9b4e2f6a1c07"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "activities",
        sa.Column(
            "thumbnail_next_attempt_at",
            sa.DateTime(timezone=True),
            nullable=True,
            comment="Earliest time the thumbnail backfill retries an activity that has no thumbnail",
        ),
    )


def downgrade() -> None:
    op.drop_column("activities", "thumbnail_next_attempt_at")
