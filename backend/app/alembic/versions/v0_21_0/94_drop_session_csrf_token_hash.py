"""94: drop the CSRF token hash of a session

The CSRF token was never checked by value on a route that mattered: a web client authenticates its requests with the
``Authorization`` header, and the one ambient credential, the refresh cookie, is read by two routes that now check
``Origin``. The token is gone, and so is the digest a session kept of it.

The downgrade adds the column back empty.

Revision ID: d94b6e2f3a58
Revises: c93f5a8d1b47
Create Date: 2026-11-13 13:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "d94b6e2f3a58"
down_revision: str | None = "c93f5a8d1b47"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Drop ``users_sessions.csrf_token_hash``."""
    op.drop_column("users_sessions", "csrf_token_hash")


def downgrade() -> None:
    """Add ``users_sessions.csrf_token_hash`` back, empty for every session."""
    op.add_column(
        "users_sessions",
        sa.Column(
            "csrf_token_hash",
            sa.String(length=255),
            nullable=True,
            comment="Hashed CSRF token for refresh validation",
        ),
    )
