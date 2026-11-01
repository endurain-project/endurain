"""15: add an optimistic-concurrency version to the users tables

Adds ``version`` to ``users`` and the per-user settings tables an edit form reads and writes, so a
client whose copy is stale is refused instead of silently reverting another client's change. The
column starts at 1 on existing rows.

Revision ID: a8d3e5c1f7b2
Revises: f2c7a9d4b1e6
Create Date: 2026-11-01 00:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a8d3e5c1f7b2"
down_revision: str | None = "f2c7a9d4b1e6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABLES = ("users", "users_privacy_settings", "users_default_gear", "users_goals")


def upgrade() -> None:
    """Add the version column to each table."""
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
    """Drop the version column from each table."""
    for table in _TABLES:
        op.drop_column(table, "version")
