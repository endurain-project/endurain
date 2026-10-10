"""15: add content_hash idempotency column to activity_media

Revision ID: 6efe1eb558f2
Revises: e5f6a7b8c9d0
Create Date: 2026-07-30 00:00:00.000000

Mirrors the activities ``dedup_key`` idempotency column: nothing previously
stopped the same photo being stored twice for one activity, whether from a
retried ``POST /activities/{id}/media`` upload or a re-run Strava bulk-export
import (its sidecar-media step has no existing-media check at all). The
existing per-row unique ``media_path`` index does not help — that value is a
server-generated storage key, always unique by construction, so it can never
catch a genuine content duplicate.

No backfill: existing rows get a ``NULL`` hash and stay unconstrained (Postgres
treats NULLs as distinct in a unique index), exactly like ``dedup_key`` was
never backfilled for file-based (as opposed to provider) activities.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "6efe1eb558f2"
down_revision: str | None = "e5f6a7b8c9d0"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "activity_media",
        sa.Column(
            "content_hash",
            sa.String(length=64),
            nullable=True,
            comment="SHA-256 of the media bytes, used to no-op re-imports of the same photo",
        ),
    )
    op.create_index(
        "uq_activity_media_activity_content_hash",
        "activity_media",
        ["activity_id", "content_hash"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("uq_activity_media_activity_content_hash", table_name="activity_media")
    op.drop_column("activity_media", "content_hash")
