"""81: record the known device a session signed in from

Forgetting a known device also signs it out, which needs each session to name the device it was opened from. The
column holds the SHA-256 hex digest of the device id, as ``known_devices`` stores it. There is no backfill: a session
that exists at the upgrade keeps null, so forgetting its device does not end it.

Revision ID: e81a5c7d0b34
Revises: d80f4b6c2e93
Create Date: 2026-11-12 00:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "e81a5c7d0b34"
down_revision: str | None = "d80f4b6c2e93"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add the nullable device hash column."""
    op.add_column(
        "users_sessions",
        sa.Column(
            "device_hash",
            sa.String(length=64),
            nullable=True,
            comment="SHA-256 hex digest of the device id the session signed in from",
        ),
    )


def downgrade() -> None:
    """Drop the device hash column."""
    op.drop_column("users_sessions", "device_hash")
