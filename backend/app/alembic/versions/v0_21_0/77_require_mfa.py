"""77: the "Require MFA" server setting

Adds ``server_settings.require_mfa``: ``off``, ``administrators`` or ``everyone``. It is ``off``, so no install
makes its users enrol a second factor until an administrator turns the requirement on.

Revision ID: a77c4e8f1b26
Revises: f76d4b8e1c35
Create Date: 2026-11-11 09:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a77c4e8f1b26"
down_revision: str | None = "f76d4b8e1c35"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add the setting, off for every existing install, and the constraint that limits it to its three values."""
    op.add_column(
        "server_settings",
        sa.Column(
            "require_mfa",
            sa.String(length=20),
            server_default="off",
            nullable=False,
            comment="Require MFA of accounts without it (off, administrators, everyone)",
        ),
    )
    op.create_check_constraint(
        "require_mfa_check", "server_settings", "require_mfa IN ('off', 'administrators', 'everyone')"
    )


def downgrade() -> None:
    """Drop the constraint and the setting."""
    op.drop_constraint("require_mfa_check", "server_settings", type_="check")
    op.drop_column("server_settings", "require_mfa")
