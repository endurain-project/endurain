"""30: widen the identity provider icon column

The icon holds a built-in key or a custom icon URL, and the form accepts a URL of up to 500 characters, which
the 100-character column and request schema rejected.

Revision ID: 2f6b9d4a8c15
Revises: 8c4e1b7d3a96
Create Date: 2026-10-30 14:00:00

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "2f6b9d4a8c15"
down_revision: str | None = "8c4e1b7d3a96"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Widen the icon column to 500 characters."""
    op.alter_column(
        "identity_providers",
        "icon",
        existing_type=sa.String(length=100),
        type_=sa.String(length=500),
        existing_nullable=True,
        existing_comment="Icon name (FontAwesome) or custom URL",
    )


def downgrade() -> None:
    """Narrow the icon column to 100 characters, clearing values that no longer fit (a cut URL is broken)."""
    op.execute("UPDATE identity_providers SET icon = NULL WHERE LENGTH(icon) > 100")
    op.alter_column(
        "identity_providers",
        "icon",
        existing_type=sa.String(length=500),
        type_=sa.String(length=100),
        existing_nullable=True,
        existing_comment="Icon name (FontAwesome) or custom URL",
    )
