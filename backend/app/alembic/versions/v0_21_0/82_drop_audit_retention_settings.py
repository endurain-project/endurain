"""82: drop the audit trail retention and legal hold settings

The audit trail is kept for the platform's default retention, with no legal hold, so ``server_settings`` no longer
stores either. The downgrade restores the columns with their defaults and the retention check constraint.

Revision ID: f82c6d1a9e57
Revises: e81a5c7d0b34
Create Date: 2026-11-12 00:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "f82c6d1a9e57"
down_revision: str | None = "e81a5c7d0b34"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Drop the retention check constraint and both columns."""
    op.drop_constraint("audit_retention_days_check", "server_settings", type_="check")
    op.drop_column("server_settings", "audit_legal_hold")
    op.drop_column("server_settings", "audit_retention_days")


def downgrade() -> None:
    """Restore both columns with their defaults and the retention check constraint."""
    op.add_column(
        "server_settings",
        sa.Column(
            "audit_retention_days",
            sa.Integer(),
            server_default=sa.text("90"),
            nullable=False,
            comment="Days after which audit trail partitions are dropped (0 - never)",
        ),
    )
    op.add_column(
        "server_settings",
        sa.Column(
            "audit_legal_hold",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
            comment="Suspend all pruning of the audit trail (true - yes, false - no)",
        ),
    )
    op.create_check_constraint(
        "audit_retention_days_check",
        "server_settings",
        "audit_retention_days = 0 OR audit_retention_days BETWEEN 30 AND 36500",
    )
