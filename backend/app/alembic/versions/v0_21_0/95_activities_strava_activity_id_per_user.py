"""95: scope the Strava activity ID of an activity to the user

``activities.strava_activity_id`` was unique across the whole table, while an activity is deduplicated per user. A
second account linking the same Strava athlete hit the constraint on every activity it imported. Provider activities
are only ever looked up for their owner, so the global constraint is replaced by a plain index on
``(user_id, strava_activity_id)`` for that lookup. Which activities a user holds once is still the
``(user_id, dedup_key)`` index.

The old constraint was created unnamed, so it is found through the inspector.

The downgrade keeps the lowest-id holder of each Strava activity ID and clears the ID of every other holder, so the
restored constraint holds.

Revision ID: e95a7c1d4b36
Revises: d94b6e2f3a58
Create Date: 2026-11-14 09:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "e95a7c1d4b36"
down_revision: str | None = "d94b6e2f3a58"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_INDEX = "ix_activities_user_id_strava_activity_id"


def upgrade() -> None:
    """Drop the table-wide unique constraint and index ``(user_id, strava_activity_id)``."""
    inspector = sa.inspect(op.get_bind())
    for constraint in inspector.get_unique_constraints("activities"):
        if constraint["column_names"] == ["strava_activity_id"]:
            op.drop_constraint(constraint["name"], "activities", type_="unique")
    op.create_index(_INDEX, "activities", ["user_id", "strava_activity_id"])


def downgrade() -> None:
    """Restore the table-wide unique constraint, clearing the ID of every holder but the lowest activity id."""
    op.drop_index(_INDEX, table_name="activities")
    op.execute(
        "UPDATE activities SET strava_activity_id = NULL WHERE id IN ("
        "SELECT id FROM (SELECT id, row_number() OVER (PARTITION BY strava_activity_id ORDER BY id) AS position "
        "FROM activities WHERE strava_activity_id IS NOT NULL) AS holders WHERE position > 1)"
    )
    op.create_unique_constraint("activities_strava_activity_id_key", "activities", ["strava_activity_id"])
