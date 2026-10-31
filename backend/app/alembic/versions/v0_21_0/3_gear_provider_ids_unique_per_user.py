"""3: scope the provider gear IDs to the user

Revision ID: c1e8a4d27b60
Revises: b7d3f5a91c24
Create Date: 2026-10-20 00:00:00.000000

``strava_gear_id`` and ``garminconnect_gear_id`` were unique across the whole table, so
one account's gear blocked another's, and a conflict revealed that someone else held the
ID. Provider gear is only ever looked up for its owner, so uniqueness moves to
``(user_id, <provider id>)``. A NULL provider ID never conflicts.

The old constraints were created unnamed, so they are found through the inspector.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "c1e8a4d27b60"
down_revision: str | None = "b7d3f5a91c24"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_COLUMNS = {
    "strava_gear_id": "uq_gear_user_strava_gear_id",
    "garminconnect_gear_id": "uq_gear_user_garminconnect_gear_id",
}


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    for constraint in inspector.get_unique_constraints("gear"):
        if len(constraint["column_names"]) == 1 and constraint["column_names"][0] in _COLUMNS:
            op.drop_constraint(constraint["name"], "gear", type_="unique")
    for column, name in _COLUMNS.items():
        op.create_unique_constraint(name, "gear", ["user_id", column])


def downgrade() -> None:
    for column, name in _COLUMNS.items():
        op.drop_constraint(name, "gear", type_="unique")
        # Two users may now hold the same provider ID; the table-wide constraint allows one
        # owner, so every later holder loses the link rather than blocking the downgrade.
        op.execute(
            f"UPDATE gear SET {column} = NULL WHERE {column} IS NOT NULL AND id NOT IN "  # noqa: S608 - column is from _COLUMNS
            f"(SELECT min(id) FROM gear WHERE {column} IS NOT NULL GROUP BY {column})"
        )
        op.create_unique_constraint(None, "gear", [column])
