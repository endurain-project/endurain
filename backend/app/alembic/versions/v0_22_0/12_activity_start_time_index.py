"""Add the index that finds a user's activities by start time

``ix_activities_user_id_start_time`` on ``(user_id, start_time)`` serves the look for the same effort an import runs:
the user's activities that start in a window before the new recording's end. Without it that look scans all of a
user's activities.

The index is built and dropped ``CONCURRENTLY`` outside the revision's transaction, so a large ``activities`` table
stays writable while it is built. A build that fails leaves an invalid index of the same name, which the next run
drops first.

Revision ID: 4f8c2b6d1a93
Revises: 9e3b7a2c5d18
Create Date: 2026-11-28 00:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "4f8c2b6d1a93"
down_revision: str | None = "9e3b7a2c5d18"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_INDEX = "ix_activities_user_id_start_time"


def upgrade() -> None:
    """Build the index without blocking writes."""
    with op.get_context().autocommit_block():
        op.execute(sa.text(f"DROP INDEX CONCURRENTLY IF EXISTS {_INDEX}"))
        op.create_index(_INDEX, "activities", ["user_id", "start_time"], postgresql_concurrently=True)


def downgrade() -> None:
    """Drop the index without blocking writes."""
    with op.get_context().autocommit_block():
        op.drop_index(_INDEX, table_name="activities", postgresql_concurrently=True, if_exists=True)
