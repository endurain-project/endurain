"""52: store a gear's initial distance in meters

``gear.initial_kms`` held kilometers while the gear's usage (``total_distance``) is in meters. The column becomes
``initial_distance`` in meters and is widened to ``Numeric(14, 2)`` so the converted values fit.

Revision ID: c3d9a5e1f478
Revises: b8c1f4a7d936
Create Date: 2026-11-06 00:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c3d9a5e1f478"
down_revision: str | None = "b8c1f4a7d936"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Widen the column, convert kilometers to meters and rename it."""
    op.alter_column(
        "gear",
        "initial_kms",
        existing_type=sa.Numeric(precision=11, scale=2),
        type_=sa.Numeric(precision=14, scale=2),
        existing_nullable=False,
    )
    op.execute("UPDATE gear SET initial_kms = initial_kms * 1000")
    op.alter_column(
        "gear",
        "initial_kms",
        new_column_name="initial_distance",
        existing_type=sa.Numeric(precision=14, scale=2),
        existing_nullable=False,
        comment="Distance of the gear before it was tracked, in meters",
    )


def downgrade() -> None:
    """Rename the column back, convert meters to kilometers and narrow it."""
    op.alter_column(
        "gear",
        "initial_distance",
        new_column_name="initial_kms",
        existing_type=sa.Numeric(precision=14, scale=2),
        existing_nullable=False,
        comment="Initial kilometers of the gear",
    )
    op.execute("UPDATE gear SET initial_kms = initial_kms / 1000")
    op.alter_column(
        "gear",
        "initial_kms",
        existing_type=sa.Numeric(precision=14, scale=2),
        type_=sa.Numeric(precision=11, scale=2),
        existing_nullable=False,
    )
