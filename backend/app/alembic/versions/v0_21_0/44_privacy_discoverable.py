"""44: let a user opt out of the username search

``users_privacy_settings.discoverable`` is the "let others find me in search" switch. Every existing row keeps
appearing in search, so the column is added switched on.

Revision ID: b5d8e2a4c371
Revises: a3e7c1b5d928
Create Date: 2026-11-05 00:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "b5d8e2a4c371"
down_revision: str | None = "a3e7c1b5d928"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add the column, switched on for every existing row."""
    op.add_column(
        "users_privacy_settings",
        sa.Column(
            "discoverable",
            sa.Boolean(),
            nullable=False,
            server_default=sa.true(),
            comment="Appear in other users' username search",
        ),
    )


def downgrade() -> None:
    """Drop the column."""
    op.drop_column("users_privacy_settings", "discoverable")
