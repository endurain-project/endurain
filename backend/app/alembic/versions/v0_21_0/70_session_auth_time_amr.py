"""70: record when and how each session's owner signed in

A session now records ``auth_time`` (when the owner signed in) and ``amr`` (how they proved themselves, as RFC 8176
values). The sessions open before this revision take their creation time and ``["pwd"]``: the methods they used were
not recorded, and a session whose sign-in used a second factor or an identity provider is not told apart.

The downgrade drops both columns.

Revision ID: a70d3b8e5f19
Revises: f69b5d8e0c24
Create Date: 2026-11-10 12:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a70d3b8e5f19"
down_revision: str | None = "f69b5d8e0c24"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABLE = "users_sessions"


def upgrade() -> None:
    """Add the sign-in time and methods, backfilled for the sessions that exist."""
    op.add_column(
        _TABLE,
        sa.Column(
            "auth_time",
            sa.DateTime(timezone=True),
            nullable=True,
            comment="When the user signed in; refresh and step-up do not change it",
        ),
    )
    op.add_column(
        _TABLE,
        sa.Column(
            "amr",
            sa.JSON(),
            nullable=True,
            comment="Authentication methods of the sign-in (RFC 8176 values): pwd, fed, otp, mfa",
        ),
    )
    op.execute(sa.text("UPDATE users_sessions SET auth_time = created_at, amr = CAST('[\"pwd\"]' AS JSON)"))
    op.alter_column(_TABLE, "auth_time", existing_type=sa.DateTime(timezone=True), nullable=False)
    op.alter_column(_TABLE, "amr", existing_type=sa.JSON(), nullable=False)


def downgrade() -> None:
    """Drop the sign-in time and methods."""
    op.drop_column(_TABLE, "amr")
    op.drop_column(_TABLE, "auth_time")
