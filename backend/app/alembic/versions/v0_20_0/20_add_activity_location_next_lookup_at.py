"""20: add activities.location_next_lookup_at

Revision ID: 9b4e2f6a1c07
Revises: 5c1d8e7a2b94
Create Date: 2026-10-15 00:00:00.000000

The reverse-geocoding backfill walks activities with no resolved location. An
activity with no GPS track, or whose coordinates resolve to nothing, stays a
candidate forever; recording when it may be looked up again keeps those rows
out of every pass instead of letting them occupy its budget. NULL means "due
now", so existing rows need no backfill.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "9b4e2f6a1c07"
down_revision: str | None = "5c1d8e7a2b94"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "activities",
        sa.Column(
            "location_next_lookup_at",
            sa.DateTime(timezone=True),
            nullable=True,
            comment="Earliest time the location backfill retries an activity with no resolved location",
        ),
    )


def downgrade() -> None:
    op.drop_column("activities", "location_next_lookup_at")
