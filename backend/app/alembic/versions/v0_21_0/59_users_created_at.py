"""59: date a user account

``users.created_at`` lets a job tell how long an account has existed, which the verification link's lifetime
alone cannot: the sign-up tokens are purged once they expire. Accounts that exist already take the migration time,
so none is mistaken for an old unverified sign-up the moment the column appears.

Revision ID: b12d4f6a8e30
Revises: a10c7e3f5d21
Create Date: 2026-11-07 10:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "b12d4f6a8e30"
down_revision: str | None = "a10c7e3f5d21"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add the creation time, now for every existing account."""
    op.add_column(
        "users",
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
            comment="When the account was created; accounts that predate the column carry the migration time",
        ),
    )


def downgrade() -> None:
    """Drop the creation time."""
    op.drop_column("users", "created_at")
