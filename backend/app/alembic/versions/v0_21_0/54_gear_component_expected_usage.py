"""54: rename gear_components.expected_kms to expected_usage

The column holds the wear threshold in meters for a distance-tracked gear and in seconds for a time-tracked one, so
its name no longer says kilometers. The values are unchanged.

Revision ID: f1b6d3a8c254
Revises: e4a7c2b9d150
Create Date: 2026-11-06 13:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "f1b6d3a8c254"
down_revision: str | None = "e4a7c2b9d150"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Rename the column and describe its units."""
    op.alter_column(
        "gear_components",
        "expected_kms",
        new_column_name="expected_usage",
        existing_type=sa.Integer(),
        existing_nullable=True,
        comment=(
            "Wear threshold of the gear component: meters for a distance-tracked gear, seconds for a time-tracked one"
        ),
    )


def downgrade() -> None:
    """Rename the column back."""
    op.alter_column(
        "gear_components",
        "expected_usage",
        new_column_name="expected_kms",
        existing_type=sa.Integer(),
        existing_nullable=True,
        comment="Expected kilometers of the gear component",
    )
