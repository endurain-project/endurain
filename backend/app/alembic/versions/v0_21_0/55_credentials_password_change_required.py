"""55: mark a password an administrator wrote as one its owner must replace

``password_change_required`` belongs to the local credential. An administrator knows the password they set or
created an account with, so the owner is asked to choose a new one at the next sign-in. Existing rows start false:
no password already stored is known to have been written by an administrator.

Revision ID: a7e3c19d5b42
Revises: f1b6d3a8c254
Create Date: 2026-11-06 14:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a7e3c19d5b42"
down_revision: str | None = "f1b6d3a8c254"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add the flag, false for every existing credential."""
    op.add_column(
        "users_local_credentials",
        sa.Column(
            "password_change_required",
            sa.Boolean(),
            server_default=sa.false(),
            nullable=False,
            comment="Whether the owner must choose a new password at the next sign-in (an administrator wrote it)",
        ),
    )


def downgrade() -> None:
    """Drop the flag."""
    op.drop_column("users_local_credentials", "password_change_required")
