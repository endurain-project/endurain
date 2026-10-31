"""13: one in-progress fast per user

A user has at most one running fast. The service looks for one before starting another, which is a
read-then-write, so two requests can both see "none" and both insert; the user then has two running
fasts and every lookup of the active one fails for good. The guarantee moves into the database as a
unique index on ``user_id`` over the in-progress rows.

Existing duplicates are resolved first: the most recently started fast of each user keeps running and
the older ones are cancelled, which keeps their rows and their start times.

The index is not built ``CONCURRENTLY``, so it blocks writes to the table while it builds. The table
holds one row per fast, so that is brief.

Revision ID: d8b4f1a7c3e5
Revises: c3e9a5d72b18
Create Date: 2026-10-30 00:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "d8b4f1a7c3e5"
down_revision: str | None = "c3e9a5d72b18"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_INDEX = "uq_health_fasting_one_in_progress_per_user"
_IN_PROGRESS = "status = 'in_progress'"
_CANCEL_OLDER = """
UPDATE health_fasting SET status = 'cancelled'
WHERE status = 'in_progress'
  AND id NOT IN (
    SELECT DISTINCT ON (user_id) id FROM health_fasting
    WHERE status = 'in_progress'
    ORDER BY user_id, fast_start_time DESC, id DESC
  )
"""


def upgrade() -> None:
    op.execute(_CANCEL_OLDER)
    op.create_index(_INDEX, "health_fasting", ["user_id"], unique=True, postgresql_where=sa.text(_IN_PROGRESS))


def downgrade() -> None:
    op.drop_index(_INDEX, table_name="health_fasting")
