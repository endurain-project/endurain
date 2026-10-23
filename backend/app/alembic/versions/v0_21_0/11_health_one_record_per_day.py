"""11: one health record per user and day

Steps, weight, sleep and water are one record per user and day. The services look for the
day's record before creating one, which is read-then-write: two requests, or a request
beside a Garmin Connect sync on another replica, can both see "not found" and both insert.
The guarantee moves into the database as a unique ``(user_id, date)`` constraint.

Existing duplicates are merged first. The newest row of a day (highest id) is kept; water is
cumulative, so the kept row takes the day's total.

``ADD CONSTRAINT ... UNIQUE`` is not concurrent, so it blocks writes to the table while it
builds. The tables hold at most one row per user and day, so that is brief.

Revision ID: a6d2f8c41e75
Revises: f4c8a2e6b7d1
Create Date: 2026-10-28 00:00:00.000000

"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a6d2f8c41e75"
down_revision: str | None = "f4c8a2e6b7d1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABLES = ("health_steps", "health_weight", "health_sleep", "health_water")

_SUM_WATER = """
    UPDATE health_water
    SET amount_ml = totals.total
    FROM (
        SELECT max(id) AS keep_id, sum(amount_ml) AS total
        FROM health_water
        GROUP BY user_id, date
        HAVING count(*) > 1
    ) totals
    WHERE health_water.id = totals.keep_id
"""

_KEEP_NEWEST = "DELETE FROM {table} WHERE id NOT IN (SELECT max(id) FROM {table} GROUP BY user_id, date)"


def upgrade() -> None:
    op.execute(_SUM_WATER)
    for table in _TABLES:
        op.execute(_KEEP_NEWEST.format(table=table))
        op.create_unique_constraint(f"uq_{table}_user_date", table, ["user_id", "date"])


def downgrade() -> None:
    for table in _TABLES:
        op.drop_constraint(f"uq_{table}_user_date", table, type_="unique")
