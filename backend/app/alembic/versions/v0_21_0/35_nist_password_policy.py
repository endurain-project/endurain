"""35: password policy follows NIST SP 800-63B-4 (length and blocklist, no composition rules)

``server_settings.password_type`` chose between a composition policy and a length-only one; the policy is now one
rule set, so the column is dropped. Both minimum lengths default to 15. An install whose lengths still sit at the old
defaults (8 for regular users, 12 for administrators) moves to 15; a length an administrator chose is kept.

Revision ID: 9e4b7a2d6c18
Revises: 2c8f5a1d7e46
Create Date: 2026-10-31 13:00:00

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "9e4b7a2d6c18"
down_revision: str | None = "2c8f5a1d7e46"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Drop ``password_type`` and move lengths still at the old defaults to 15."""
    op.drop_column("server_settings", "password_type")
    for column in ("password_length_regular_users", "password_length_admin_users"):
        op.alter_column(
            "server_settings",
            column,
            existing_type=sa.Integer(),
            existing_nullable=False,
            server_default=sa.text("15"),
        )
    op.execute("UPDATE server_settings SET password_length_regular_users = 15 WHERE password_length_regular_users = 8")
    op.execute("UPDATE server_settings SET password_length_admin_users = 15 WHERE password_length_admin_users = 12")


def downgrade() -> None:
    """Re-add ``password_type`` as 'strict' and drop the length defaults.

    The lengths are not reverted: a 15 could be the new default or a value an administrator chose.
    """
    op.add_column(
        "server_settings",
        sa.Column(
            "password_type",
            sa.String(),
            nullable=False,
            server_default="strict",
            comment="Password type policy (strict, length_only)",
        ),
    )
    op.alter_column("server_settings", "password_type", existing_type=sa.String(), server_default=None)
    for column in ("password_length_regular_users", "password_length_admin_users"):
        op.alter_column(
            "server_settings",
            column,
            existing_type=sa.Integer(),
            existing_nullable=False,
            server_default=None,
        )
