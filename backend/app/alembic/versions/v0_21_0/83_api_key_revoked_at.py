"""83: record when an API key was revoked

The purge of stale API keys needs the moment a key was revoked, which ``is_active`` alone does not hold. A key that is
already revoked at the upgrade takes the upgrade time, the latest instant it can have been revoked, so it is kept
for the full retention period before the purge and is never deleted at once because it was created long ago.

Revision ID: a83d7e2c5f19
Revises: f82c6d1a9e57
Create Date: 2026-11-12 01:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a83d7e2c5f19"
down_revision: str | None = "f82c6d1a9e57"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add the nullable revocation time and backfill the keys already revoked."""
    op.add_column(
        "users_api_keys",
        sa.Column(
            "revoked_at",
            sa.DateTime(timezone=True),
            nullable=True,
            comment="When the key was revoked; null while it has not been",
        ),
    )
    op.execute("UPDATE users_api_keys SET revoked_at = now() WHERE is_active = false")


def downgrade() -> None:
    """Drop the revocation time column."""
    op.drop_column("users_api_keys", "revoked_at")
