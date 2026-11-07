"""17: let an ingestion refresh wait for a provider's rate limit

A refresh that hits a provider's rate limit is now deferred until the limit clears instead of
failing, so its job row records when it runs again.

Revision ID: c9a2e7d4b1f6
Revises: b4f1c8e2a7d9
Create Date: 2026-11-03 00:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c9a2e7d4b1f6"
down_revision: str | None = "b4f1c8e2a7d9"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add the instant a deferred refresh runs again."""
    op.add_column(
        "activity_ingestion_jobs",
        sa.Column(
            "retry_after",
            sa.DateTime(timezone=True),
            nullable=True,
            comment="When a deferred refresh runs again; a provider's rate limit clears then",
        ),
    )
    op.alter_column(
        "activity_ingestion_jobs",
        "status",
        existing_type=sa.String(length=20),
        existing_nullable=False,
        existing_server_default="pending",
        comment="pending | processing | deferred | completed | failed",
    )


def downgrade() -> None:
    """Fail the deferred refreshes and drop the column.

    A deferred refresh has no meaning without the column, so each becomes failed rather than
    stuck waiting for a sweep that no longer exists.
    """
    op.execute(
        "UPDATE activity_ingestion_jobs SET status = 'failed', error_code = 'provider_unavailable', "
        "completed_at = now(), updated_at = now() WHERE status = 'deferred'"
    )
    op.alter_column(
        "activity_ingestion_jobs",
        "status",
        existing_type=sa.String(length=20),
        existing_nullable=False,
        existing_server_default="pending",
        comment="pending | processing | completed | failed",
    )
    op.drop_column("activity_ingestion_jobs", "retry_after")
