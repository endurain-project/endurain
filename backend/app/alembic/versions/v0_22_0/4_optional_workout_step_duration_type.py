"""Let a workout step have no duration type

A FIT workout step need not name its duration type, and such a step made the whole file fail to import because the
column was ``NOT NULL``. The column now holds null for a step that names none.

The downgrade deletes the steps without a duration type, which v0.21 could not have imported, and restores
``NOT NULL``.

Revision ID: 3c9e5a7d1f20
Revises: 8d2f61b0c7a4
Create Date: 2026-11-23 00:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "3c9e5a7d1f20"
down_revision: str | None = "8d2f61b0c7a4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Drop ``NOT NULL`` from ``activity_workout_steps.duration_type``."""
    op.alter_column("activity_workout_steps", "duration_type", existing_type=sa.String(250), nullable=True)


def downgrade() -> None:
    """Delete the steps without a duration type and restore ``NOT NULL``."""
    op.execute(sa.text("DELETE FROM activity_workout_steps WHERE duration_type IS NULL"))
    op.alter_column("activity_workout_steps", "duration_type", existing_type=sa.String(250), nullable=False)
