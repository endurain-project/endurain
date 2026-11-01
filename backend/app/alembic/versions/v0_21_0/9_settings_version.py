"""9: add an optimistic-concurrency version to the settings rows

Adds ``version`` to ``server_settings`` and ``mail_settings`` so an admin whose form is stale is
refused instead of silently reverting another admin's change.

Revision ID: e3b7a5d1c968
Revises: d7a1c9e3f452
Create Date: 2026-10-26 00:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "e3b7a5d1c968"
down_revision: str | None = "d7a1c9e3f452"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABLES = ("server_settings", "mail_settings")


def upgrade() -> None:
    """Add the version column to both settings tables."""
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
    """Drop the version column from both settings tables."""
    for table in _TABLES:
        op.drop_column(table, "version")
