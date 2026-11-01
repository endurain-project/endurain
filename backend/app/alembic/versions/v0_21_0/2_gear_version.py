"""2: add the gear and gear component optimistic-concurrency version columns

Revision ID: b7d3f5a91c24
Revises: 9a4e6c2d1f73
Create Date: 2026-10-20 00:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "b7d3f5a91c24"
down_revision: str | None = "9a4e6c2d1f73"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABLES = ("gear", "gear_components")


def upgrade() -> None:
    """Add the version counter backing ETag/If-Match on gears and their components."""
    for table in _TABLES:
        op.add_column(
            table,
            sa.Column(
                "version",
                sa.Integer(),
                nullable=False,
                server_default="1",
                comment="Optimistic-concurrency counter, surfaced to clients as the ETag",
            ),
        )


def downgrade() -> None:
    """Remove the version counters."""
    for table in reversed(_TABLES):
        op.drop_column(table, "version")
