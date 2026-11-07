"""21: one goal per user, interval, activity type and goal type

A user has one goal for each combination of interval, activity type and goal type. The rule was a
read before the insert, so two concurrent requests could both create the goal, and an edit could change
a goal into another one without the check running. The guarantee moves into the database.

Existing duplicates are removed first, keeping the newest goal (highest id) of each combination. A goal
holds only its own targets, so nothing else points at it.

``ADD CONSTRAINT ... UNIQUE`` is not concurrent, so it blocks writes to the table while it builds. A
user has a handful of goals, so that is brief.

Revision ID: 4d8b2f6a91c3
Revises: c91b4e7a2d60
Create Date: 2026-10-29 00:00:00.000000

"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "4d8b2f6a91c3"
down_revision: str | None = "c91b4e7a2d60"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_KEEP_NEWEST = (
    "DELETE FROM users_goals WHERE id NOT IN "
    "(SELECT max(id) FROM users_goals GROUP BY user_id, interval, activity_type, goal_type)"
)


def upgrade() -> None:
    op.execute(_KEEP_NEWEST)
    op.create_unique_constraint(
        "uq_users_goals_user_scope", "users_goals", ["user_id", "interval", "activity_type", "goal_type"]
    )


def downgrade() -> None:
    op.drop_constraint("uq_users_goals_user_scope", "users_goals", type_="unique")
