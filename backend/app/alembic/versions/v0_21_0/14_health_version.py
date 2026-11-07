"""14: add an optimistic-concurrency version to the health tables

Adds ``version`` to every health table so a client whose copy is stale is refused instead of
silently reverting another client's change. The column starts at 1 on existing rows.

Revision ID: f2c7a9d4b1e6
Revises: d8b4f1a7c3e5
Create Date: 2026-10-31 00:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "f2c7a9d4b1e6"
down_revision: str | None = "d8b4f1a7c3e5"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABLES = (
    "health_weight",
    "health_water",
    "health_steps",
    "health_sleep",
    "health_poop",
    "health_fasting",
    "health_targets",
)


def upgrade() -> None:
    """Add the version column to every health table."""
    for table in _TABLES:
        op.add_column(
            table,
            sa.Column(
                "version",
                sa.Integer(),
                server_default=sa.text("1"),
                nullable=False,
                comment="Optimistic-concurrency counter, surfaced to clients as the ETag",
            ),
        )


def downgrade() -> None:
    """Drop the version column from every health table."""
    for table in _TABLES:
        op.drop_column(table, "version")
