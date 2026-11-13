"""79: drop the unused identity provider jwks_uri

Sign-in and back-channel logout take the signing keys from the provider's discovery document, never from this
column, so the column and the field that filled it are removed.

Revision ID: c79e3a5d1b82
Revises: b78d2f6a9c41
Create Date: 2026-11-11 19:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c79e3a5d1b82"
down_revision: str | None = "b78d2f6a9c41"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Drop the jwks_uri column."""
    op.drop_column("identity_providers", "jwks_uri")


def downgrade() -> None:
    """Add the jwks_uri column back, empty: the dropped values are not kept."""
    op.add_column(
        "identity_providers",
        sa.Column("jwks_uri", sa.String(length=500), nullable=True, comment="OIDC JWKS URI for token verification"),
    )
