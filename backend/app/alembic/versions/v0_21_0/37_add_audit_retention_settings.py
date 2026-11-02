"""37: store the audit trail retention and legal hold in the database

Adds ``audit_retention_days`` and ``audit_legal_hold`` to ``server_settings``, so an
administrator edits them at run time. A retention is 0 (keep everything) or between the
audit trail's database-side floor of 30 days and the substrate's maximum of 36500 days.

Revision ID: 4f2b8c6e1a93
Revises: d0aa98611b9c
Create Date: 2026-11-02 00:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "4f2b8c6e1a93"
down_revision: str | None = "d0aa98611b9c"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add the audit retention and legal hold columns and the retention check constraint."""
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


def downgrade() -> None:
    """Drop the check constraint and both columns."""
    op.drop_constraint("audit_retention_days_check", "server_settings", type_="check")
    op.drop_column("server_settings", "audit_legal_hold")
    op.drop_column("server_settings", "audit_retention_days")
