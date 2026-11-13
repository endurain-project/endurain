"""62: bind each rotated refresh token to the client that rotated it

A rotated refresh token presented again inside the grace window used to be answered with the live replacement
refresh token whoever presented it. The rotated record now stores a fingerprint of the rotating client, its network
and its ``User-Agent``, and only a retry from the same client is answered. The existing records carry no fingerprint
and are deleted: the sessions they belong to were ended by revision 58, so no rotated token of them can be presented
again.

The downgrade drops the column.

Revision ID: b62d4f8a1c75
Revises: e61b7c3d9a40
Create Date: 2026-11-08 09:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "b62d4f8a1c75"
down_revision: str | None = "e61b7c3d9a40"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABLE = "rotated_refresh_tokens"


def upgrade() -> None:
    """Delete the rotated records, which have no fingerprint, then add the non-null client fingerprint."""
    op.execute("DELETE FROM rotated_refresh_tokens")
    op.add_column(
        _TABLE,
        sa.Column(
            "client_fingerprint",
            sa.String(length=64),
            nullable=False,
            comment="SHA-256 hex of the rotating client's network and User-Agent, joined by a newline",
        ),
    )


def downgrade() -> None:
    """Drop the client fingerprint."""
    op.drop_column(_TABLE, "client_fingerprint")
