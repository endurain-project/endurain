"""23: scope a refresh job to a provider and window

Revision ID: 3d7b5e9a2c64
Revises: e1f4a8c6b3d9
Create Date: 2026-10-15 00:00:00.000000

A refresh used to sync every linked provider over the last day. The provider
sync endpoints take an explicit date range for one provider, and those now run as
the same job instead of in the API process, so the job records which provider and
which window it was asked for. NULL keeps the old meaning, so existing rows need
no backfill.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "3d7b5e9a2c64"
down_revision: str | None = "e1f4a8c6b3d9"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "activity_ingestion_jobs",
        sa.Column(
            "provider",
            sa.String(length=50),
            nullable=True,
            comment="Provider a refresh syncs; null syncs every linked provider",
        ),
    )
    op.add_column(
        "activity_ingestion_jobs",
        sa.Column(
            "window_start",
            sa.DateTime(timezone=True),
            nullable=True,
            comment="Start of the window a refresh fetches; null means the default window",
        ),
    )
    op.add_column(
        "activity_ingestion_jobs",
        sa.Column(
            "window_end",
            sa.DateTime(timezone=True),
            nullable=True,
            comment="End of the window a refresh fetches",
        ),
    )


def downgrade() -> None:
    op.drop_column("activity_ingestion_jobs", "window_end")
    op.drop_column("activity_ingestion_jobs", "window_start")
    op.drop_column("activity_ingestion_jobs", "provider")
