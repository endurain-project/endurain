"""34: describe rotated_refresh_tokens.expires_at as the end of the replay grace window

Only the column comment changes; no data or type is touched.

Revision ID: 2c8f5a1d7e46
Revises: 7a3d94c1e8b5
Create Date: 2026-10-31 12:00:00

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "2c8f5a1d7e46"
down_revision: str | None = "7a3d94c1e8b5"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_NEW_COMMENT = "End of the replay grace window"
_OLD_COMMENT = "Cleanup marker (rotated_at + 60 seconds)"


def upgrade() -> None:
    """Describe ``expires_at`` as the end of the replay grace window."""
    op.alter_column(
        "rotated_refresh_tokens",
        "expires_at",
        existing_type=sa.DateTime(timezone=True),
        existing_nullable=False,
        comment=_NEW_COMMENT,
    )


def downgrade() -> None:
    """Restore the previous ``expires_at`` comment."""
    op.alter_column(
        "rotated_refresh_tokens",
        "expires_at",
        existing_type=sa.DateTime(timezone=True),
        existing_nullable=False,
        comment=_OLD_COMMENT,
    )
