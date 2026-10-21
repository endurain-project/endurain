"""4: index notifications by user and creation date

The notifications list is read per user, newest first. The composite index serves
that ordering and covers the lookups the single ``user_id`` index served, so it is
dropped. A partial index on the creation date of read rows serves the daily retention
purge, which would otherwise scan the table for every batch.

Both indexes are built ``CONCURRENTLY`` outside the migration transaction, so writes to
``notifications`` are not blocked while they build.

Revision ID: e3a7c91f5d28
Revises: c1e8a4d27b60
Create Date: 2026-10-21 00:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "e3a7c91f5d28"
down_revision: str | None = "c1e8a4d27b60"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Swap the user index for the user and creation date index and add the purge index."""
    with op.get_context().autocommit_block():
        op.create_index(
            "ix_notifications_user_id_created_at",
            "notifications",
            ["user_id", "created_at"],
            postgresql_concurrently=True,
            if_not_exists=True,
        )
        op.create_index(
            "ix_notifications_read_created_at",
            "notifications",
            ["created_at"],
            postgresql_where=sa.text("read"),
            postgresql_concurrently=True,
            if_not_exists=True,
        )
        op.drop_index(
            "ix_notifications_user_id", table_name="notifications", postgresql_concurrently=True, if_exists=True
        )


def downgrade() -> None:
    """Restore the single-column user index."""
    with op.get_context().autocommit_block():
        op.create_index(
            "ix_notifications_user_id",
            "notifications",
            ["user_id"],
            postgresql_concurrently=True,
            if_not_exists=True,
        )
        op.drop_index(
            "ix_notifications_read_created_at", table_name="notifications", postgresql_concurrently=True, if_exists=True
        )
        op.drop_index(
            "ix_notifications_user_id_created_at",
            table_name="notifications",
            postgresql_concurrently=True,
            if_exists=True,
        )
