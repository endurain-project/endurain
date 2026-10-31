"""32: add users.weight_units

Body weight was always presented in the unit system of ``users.units``, which also drives
distance, pace, elevation and temperature. Users who mix systems — the canonical example being
Canada, where running distances are discussed in kilometres but body weight in pounds — had no
way to split the two. ``weight_units`` overrides the system for body weight only, leaving
distance, pace, elevation and temperature on ``users.units``.

Nullable with no backfill. ``NULL`` means "not set" and displays exactly as before: weight
follows ``users.units``. Nothing changes for existing users.

Revision ID: 7a3d94c1e8b5
Revises: 6d3a8f1c5e92
Create Date: 2026-10-31 12:00:00

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "7a3d94c1e8b5"
down_revision: str | None = "6d3a8f1c5e92"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add the weight units override, unset for every existing user."""
    op.add_column(
        "users",
        sa.Column(
            "weight_units",
            sa.String(length=20),
            nullable=True,
            comment="User weight units override (metric - kg, imperial - lb), null follows units",
        ),
    )


def downgrade() -> None:
    """Drop the weight units override."""
    op.drop_column("users", "weight_units")
