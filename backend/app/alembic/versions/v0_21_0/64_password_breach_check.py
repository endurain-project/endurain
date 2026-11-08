"""64: opt-in breached-password check

Adds ``server_settings.password_breach_check_enabled``. It is off, so no install starts sending password hash
prefixes to a third party without an administrator turning the check on.

Revision ID: d64f2b3c4e5a
Revises: c63e1a2b3d4f
Create Date: 2026-11-08 12:00:00

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "d64f2b3c4e5a"
down_revision: str | None = "c63e1a2b3d4f"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add the switch, off for every existing install."""
    op.add_column(
        "server_settings",
        sa.Column(
            "password_breach_check_enabled",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
            comment="Refuse new passwords found in a known data breach (true - yes, false - no)",
        ),
    )


def downgrade() -> None:
    """Drop the switch."""
    op.drop_column("server_settings", "password_breach_check_enabled")
