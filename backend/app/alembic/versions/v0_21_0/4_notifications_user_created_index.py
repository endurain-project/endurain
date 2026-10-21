"""4: index notifications by user and creation date

The notifications list is read per user, newest first. The composite index serves
that ordering and covers the lookups the single ``user_id`` index served, so it is
dropped.

Revision ID: e3a7c91f5d28
Revises: c1e8a4d27b60
Create Date: 2026-10-21 00:00:00.000000

"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "e3a7c91f5d28"
down_revision: str | None = "c1e8a4d27b60"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Swap the user index for the user and creation date index."""
    op.create_index("ix_notifications_user_id_created_at", "notifications", ["user_id", "created_at"])
    op.drop_index("ix_notifications_user_id", table_name="notifications")


def downgrade() -> None:
    """Restore the single-column user index."""
    op.create_index("ix_notifications_user_id", "notifications", ["user_id"])
    op.drop_index("ix_notifications_user_id_created_at", table_name="notifications")
