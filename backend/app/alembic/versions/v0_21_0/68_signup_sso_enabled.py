"""68: add the switch that allows sign-up through single sign-on

Adds ``signup_sso_enabled`` to ``server_settings``. It is off for every existing install, so an upgrade stops
identity providers from creating accounts until an administrator turns it on; linking and signing in to existing
accounts is unaffected.

Revision ID: e68a4c7d9b13
Revises: 3f7a9c1e5b82
Create Date: 2026-11-10 00:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "e68a4c7d9b13"
down_revision: str | None = "3f7a9c1e5b82"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add the SSO sign-up switch, off."""
    op.add_column(
        "server_settings",
        sa.Column(
            "signup_sso_enabled",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
            comment="Allow identity providers to create accounts at first sign-in (true - yes, false - no)",
        ),
    )


def downgrade() -> None:
    """Drop the SSO sign-up switch."""
    op.drop_column("server_settings", "signup_sso_enabled")
