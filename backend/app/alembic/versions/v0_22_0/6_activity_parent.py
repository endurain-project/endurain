"""Link the legs of a multisport activity to their parent

A multisport file is stored as one parent activity and its legs, which are ordinary activities. Each leg names its
parent in ``activities.parent_activity_id``; the parent itself has none. Deleting a parent deletes its legs, and an
activity cannot be its own parent.

The downgrade deletes the parents (activity type 48) and keeps their legs as stand-alone activities, because v0.21
has no parent to attach them to and would count the parent's totals a second time.

Revision ID: daa50e9181bb
Revises: 86ddd2645a0c
Create Date: 2026-11-25 00:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "daa50e9181bb"
down_revision: str | None = "86ddd2645a0c"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

#: The stored ``ActivityType.MULTISPORT``.
_MULTISPORT = 48


def upgrade() -> None:
    """Add ``parent_activity_id`` with its cascading key, its index and the not-self check."""
    op.add_column(
        "activities",
        sa.Column(
            "parent_activity_id",
            sa.Uuid(),
            sa.ForeignKey("activities.id", ondelete="CASCADE"),
            nullable=True,
            comment="Multisport parent activity ID, set on a leg and null on every other activity",
        ),
    )
    op.create_check_constraint("ck_activities_parent_not_self", "activities", "parent_activity_id <> id")
    op.create_index(
        "ix_activities_user_id_parent_activity_id", "activities", ["user_id", "parent_activity_id"], unique=False
    )


def downgrade() -> None:
    """Delete the multisport parents, keep their legs as activities and drop ``parent_activity_id`` with its key."""
    op.execute(sa.text("UPDATE activities SET parent_activity_id = NULL WHERE parent_activity_id IS NOT NULL"))
    op.execute(sa.text("DELETE FROM activities WHERE activity_type = :multisport").bindparams(multisport=_MULTISPORT))
    op.drop_index("ix_activities_user_id_parent_activity_id", table_name="activities")
    op.drop_constraint("ck_activities_parent_not_self", "activities", type_="check")
    op.drop_column("activities", "parent_activity_id")
