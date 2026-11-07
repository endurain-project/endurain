"""8: store the read-notification retention in the database

Adds ``read_notification_retention_days`` to ``server_settings``. The server default equals
the default of ``READ_NOTIFICATION_RETENTION_DAYS``; an install that sets it has it imported
on the next API start.

Revision ID: d7a1c9e3f452
Revises: b5e8d2c4a916
Create Date: 2026-10-25 00:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "d7a1c9e3f452"
down_revision: str | None = "b5e8d2c4a916"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add the retention column and its range check constraint."""
    op.add_column(
        "server_settings",
        sa.Column(
            "read_notification_retention_days",
            sa.Integer(),
            server_default=sa.text("90"),
            nullable=False,
            comment="Days after which read notifications are purged (0 - never)",
        ),
    )
    op.create_check_constraint(
        "read_notification_retention_days_check",
        "server_settings",
        "read_notification_retention_days BETWEEN 0 AND 3650",
    )


def downgrade() -> None:
    """Drop the retention column."""
    op.drop_constraint("read_notification_retention_days_check", "server_settings", type_="check")
    op.drop_column("server_settings", "read_notification_retention_days")
