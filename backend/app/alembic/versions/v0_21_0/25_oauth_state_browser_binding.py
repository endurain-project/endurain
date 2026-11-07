"""25: bind an identity-provider link to the browser that started it

A link's OAuth state now stores the SHA-256 of a secret the starting browser keeps in a cookie, and the
callback refuses a link that another browser finishes. Without it, the provider URL of a link an
attacker started on their own account would bind any victim who opened it to that account.

States are short-lived, so existing rows are left without a binding: a link begun before the upgrade
must be started again.

Revision ID: 5f1a8c3e9b27
Revises: 8c4e2a6f0d93
Create Date: 2026-10-29 00:00:00

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "5f1a8c3e9b27"
down_revision: str | None = "8c4e2a6f0d93"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add the link's browser-binding digest."""
    op.add_column(
        "oauth_states",
        sa.Column(
            "browser_binding_hash",
            sa.String(length=64),
            nullable=True,
            comment="SHA-256 of the link's browser-binding cookie (link mode only)",
        ),
    )


def downgrade() -> None:
    """Drop the link's browser-binding digest."""
    op.drop_column("oauth_states", "browser_binding_hash")
