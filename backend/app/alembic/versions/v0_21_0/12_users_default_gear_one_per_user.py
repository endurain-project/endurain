"""12: one default-gear row per user

A user has one set of default gear. The rows are created on demand by a read-then-write, so two
requests can both see "not found" and both insert; the user then has two rows and every lookup
that expects one fails for good. The guarantee moves into the database as a unique ``user_id``.

Existing duplicates are removed first, keeping the newest row (highest id) of each user. The row
holds only references to gear, so nothing else points at it.

``ADD CONSTRAINT ... UNIQUE`` is not concurrent, so it blocks writes to the table while it
builds. The table holds one row per user, so that is brief.

Revision ID: c3e9a5d72b18
Revises: a6d2f8c41e75
Create Date: 2026-10-29 00:00:00.000000

"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c3e9a5d72b18"
down_revision: str | None = "a6d2f8c41e75"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_KEEP_NEWEST = (
    "DELETE FROM users_default_gear WHERE id NOT IN (SELECT max(id) FROM users_default_gear GROUP BY user_id)"
)


def upgrade() -> None:
    op.execute(_KEEP_NEWEST)
    op.create_unique_constraint("uq_users_default_gear_user_id", "users_default_gear", ["user_id"])


def downgrade() -> None:
    op.drop_constraint("uq_users_default_gear_user_id", "users_default_gear", type_="unique")
