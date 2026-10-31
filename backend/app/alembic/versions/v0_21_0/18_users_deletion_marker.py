"""18: record that an account is queued for deletion

An account deletion is a background job, and a job that failed for good or whose in-process worker was
lost leaves the account deactivated with nothing saying it is meant to go. ``deletion_requested_at``
marks it, so a sweep can queue the deletion again, and ``deletion_attempts`` caps how often it does.

Revision ID: d5b8f1a3c7e2
Revises: c9a2e7d4b1f6
Create Date: 2026-11-04 00:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "d5b8f1a3c7e2"
down_revision: str | None = "c9a2e7d4b1f6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add the deletion marker and the attempt counter."""
    op.add_column(
        "users",
        sa.Column(
            "deletion_requested_at",
            sa.DateTime(timezone=True),
            nullable=True,
            comment="When the account was queued for deletion; null for an account that is not being deleted",
        ),
    )
    op.add_column(
        "users",
        sa.Column(
            "deletion_attempts",
            sa.Integer(),
            server_default=sa.text("0"),
            nullable=False,
            comment="How many times the sweep queued this account's deletion again",
        ),
    )


def downgrade() -> None:
    """Drop the deletion marker and the attempt counter."""
    op.drop_column("users", "deletion_attempts")
    op.drop_column("users", "deletion_requested_at")
