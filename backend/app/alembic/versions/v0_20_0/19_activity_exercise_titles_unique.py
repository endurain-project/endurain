"""19: enforce activity exercise title uniqueness

Revision ID: 5c1d8e7a2b94
Revises: e3b7a91c4d62
Create Date: 2026-10-14 00:00:00.000000

The exercise-title insert checks for existing ``(exercise_category,
exercise_name)`` pairs before inserting, which is read-then-write: two concurrent
imports can both see "not found" and both insert. The guarantee moves into the
database.

The table is a reference lookup that nothing references, so existing duplicates
are removed, keeping the lowest id of each pair.

"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "5c1d8e7a2b94"
down_revision: str | None = "e3b7a91c4d62"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        DELETE FROM activity_exercise_titles
        WHERE id IN (
            SELECT id FROM (
                SELECT id,
                       ROW_NUMBER() OVER (
                           PARTITION BY exercise_category, exercise_name ORDER BY id
                       ) AS row_position
                FROM activity_exercise_titles
            ) ranked
            WHERE ranked.row_position > 1
        )
        """
    )
    op.create_unique_constraint(
        "uq_activity_exercise_titles_category_name",
        "activity_exercise_titles",
        ["exercise_category", "exercise_name"],
    )


def downgrade() -> None:
    op.drop_constraint(
        "uq_activity_exercise_titles_category_name",
        "activity_exercise_titles",
        type_="unique",
    )
