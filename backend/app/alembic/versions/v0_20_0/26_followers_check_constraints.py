"""26: enforce follower invariants in the database

Revision ID: 6f2d8b4e1a97
Revises: 4c9e1a7d3b52
Create Date: 2026-10-18 00:00:00.000000

Self-follows and unknown statuses were refused only by the service, so a second
writer (a script, another replica running older code) could store them. Both
rules become check constraints. A self-follow row is meaningless, so any that
exist are removed before the constraint is added.
"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "6f2d8b4e1a97"
down_revision: str | None = "4c9e1a7d3b52"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("DELETE FROM followers WHERE follower_id = followee_id")
    op.create_check_constraint("ck_followers_not_self", "followers", "follower_id <> followee_id")
    op.create_check_constraint("ck_followers_status", "followers", "status IN ('pending', 'accepted')")


def downgrade() -> None:
    op.drop_constraint("ck_followers_status", "followers", type_="check")
    op.drop_constraint("ck_followers_not_self", "followers", type_="check")
