"""22: drop activities_streams.zone_percentages

Revision ID: e1f4a8c6b3d9
Revises: c4a7d92e5b18
Create Date: 2026-10-15 00:00:00.000000

Heart-rate zones are a function of the samples and the owner's *current* max heart
rate (itself derived from their age), so a stored copy goes stale on every profile
edit and every birthday. They are computed when a stream is served instead, and the
column, its backfill (data migration 7) and its recompute are gone.

Migration 7 is marked executed: there is nothing left for it to backfill, and an
installation upgrading from before v0.19.0 would otherwise run a handler that no
longer exists.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "e1f4a8c6b3d9"
down_revision: str | None = "c4a7d92e5b18"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_column("activities_streams", "zone_percentages")
    op.execute("UPDATE migrations SET executed = true WHERE id = 7")


def downgrade() -> None:
    op.add_column(
        "activities_streams",
        sa.Column(
            "zone_percentages",
            sa.JSON(),
            nullable=True,
            comment="Pre-computed zone breakdowns keyed by metric (e.g. 'hr')",
        ),
    )
    # The column is empty again; the release that reads it backfills it on start.
    op.execute("UPDATE migrations SET executed = false WHERE id = 7")
