"""22: add an optimistic-concurrency version to user integrations

Adds a version counter so a change to a user's Strava client credentials is refused when another request
has changed the row since the client read it. Existing rows start at 1.

Revision ID: 7e2c5a9f4b18
Revises: 4d8b2f6a91c3
Create Date: 2026-10-29 00:00:00

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "7e2c5a9f4b18"
down_revision: str | None = "4d8b2f6a91c3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add the version column to user integrations."""
    op.add_column(
        "users_integrations",
        sa.Column(
            "version",
            sa.Integer(),
            server_default=sa.text("1"),
            nullable=False,
            comment="Optimistic-concurrency counter, surfaced to clients as the ETag",
        ),
    )


def downgrade() -> None:
    """Drop the user-integrations version column."""
    op.drop_column("users_integrations", "version")
