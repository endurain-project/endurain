"""74: index the rotated tokens whose replacement is still stored

The purge job clears the replacement refresh token of records whose grace window has ended, one bounded batch at
a time. A partial index on the end of the grace window, limited to records that still hold a replacement, lets
each batch find them without scanning the table; once cleared a record leaves the index.

The index is built ``CONCURRENTLY`` outside the migration transaction, so rotations are not blocked while it builds.

Revision ID: d74b8f2c6a13
Revises: c73a6e1b4d92
Create Date: 2026-11-10 17:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "d74b8f2c6a13"
down_revision: str | None = "c73a6e1b4d92"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_INDEX = "ix_rotated_refresh_tokens_expires_at_with_replacement"


def upgrade() -> None:
    """Create the partial index on the end of the grace window."""
    with op.get_context().autocommit_block():
        op.create_index(
            _INDEX,
            "rotated_refresh_tokens",
            ["expires_at"],
            postgresql_where=sa.text("replacement_refresh_token IS NOT NULL"),
            postgresql_concurrently=True,
            if_not_exists=True,
        )


def downgrade() -> None:
    """Drop the partial index."""
    with op.get_context().autocommit_block():
        op.drop_index(_INDEX, table_name="rotated_refresh_tokens", postgresql_concurrently=True, if_exists=True)
