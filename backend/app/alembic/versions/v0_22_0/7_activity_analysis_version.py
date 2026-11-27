"""Record the analysis version of each activity and queue the v0.22 reprocess

``activities.analysis_version`` is the version of the file analysis that computed an activity's derived values. A row
that existed before versions is 0, so the reprocess data migration, which walks the activities below the current
version in ``(analysis_version, id)`` order, visits every one of them.

The upgrade registers that data migration as pending (id 15). The downgrade deletes the row, drops the index and the
column; values the reprocess already recomputed stay as they are.

Revision ID: 069908f3eab8
Revises: daa50e9181bb
Create Date: 2026-11-27 00:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "069908f3eab8"
down_revision: str | None = "daa50e9181bb"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

#: The ``migrations`` row of the reprocess data migration.
_REPROCESS_MIGRATION_ID = 15


def upgrade() -> None:
    """Add ``analysis_version`` and its keyset index, and register the pending reprocess data migration."""
    op.add_column(
        "activities",
        sa.Column(
            "analysis_version",
            sa.SmallInteger(),
            nullable=False,
            server_default="0",
            comment=(
                "The version of the file analysis that computed the activity's derived values; 0 for one computed "
                "before versions existed"
            ),
        ),
    )
    op.create_index("ix_activities_analysis_version_id", "activities", ["analysis_version", "id"], unique=False)
    op.execute(
        sa.text(
            "INSERT INTO migrations (id, name, description, executed) VALUES "
            "(:id, 'v0.22.0', 'Reprocess activities from their retained files with the v0.22 analysis', false)"
        ).bindparams(id=_REPROCESS_MIGRATION_ID)
    )


def downgrade() -> None:
    """Delete the reprocess data migration row, drop the index and drop ``analysis_version``."""
    op.execute(sa.text("DELETE FROM migrations WHERE id = :id").bindparams(id=_REPROCESS_MIGRATION_ID))
    op.drop_index("ix_activities_analysis_version_id", table_name="activities")
    op.drop_column("activities", "analysis_version")
