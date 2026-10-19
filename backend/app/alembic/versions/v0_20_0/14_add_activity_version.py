"""14: add the activities optimistic-concurrency version column

Revision ID: e5f6a7b8c9d0
Revises: d4e5f6a7b8c9
Create Date: 2026-07-29 00:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "e5f6a7b8c9d0"
down_revision: str | None = "d4e5f6a7b8c9"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add the version counter backing ETag/If-Match on activities."""
    op.add_column(
        "activities",
        sa.Column(
            "version",
            sa.Integer(),
            nullable=False,
            server_default="1",
            comment="Optimistic-concurrency counter, surfaced to clients as the ETag",
        ),
    )


def downgrade() -> None:
    """Remove the version counter."""
    op.drop_column("activities", "version")
