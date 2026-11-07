"""20: add an optimistic-concurrency version to identity providers

Adds a version counter so an identity-provider edit is refused when another admin
has changed the provider since the editor loaded it. Existing rows start at 1.

Revision ID: c91b4e7a2d60
Revises: e6a3b8d1f2c4
Create Date: 2026-10-28 00:00:00

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "c91b4e7a2d60"
down_revision: str | None = "e6a3b8d1f2c4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add the version column to identity providers."""
    op.add_column(
        "identity_providers",
        sa.Column(
            "version",
            sa.Integer(),
            server_default=sa.text("1"),
            nullable=False,
            comment="Optimistic-concurrency counter, surfaced to clients as the ETag",
        ),
    )


def downgrade() -> None:
    """Drop the identity-provider version column."""
    op.drop_column("identity_providers", "version")
