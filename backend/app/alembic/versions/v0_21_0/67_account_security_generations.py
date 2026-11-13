"""67: add account_security_generations and the generation an OAuth state was started under

Each row holds an account's security generation, a counter advanced by every security change. A proof that is
pending when the change commits records the generation it was created under and stops being redeemable. There is no
backfill: an account without a row is at generation 0, and its row is created by the first security change or the
first redeem that checks it. ``oauth_states.security_generation`` records the generation of a link, step-up or
pending-exchange flow; existing states keep null and are refused when redeemed, which only ends flows that were
pending at the upgrade. ``oauth_states.ends_other_sessions`` records whether a link's callback ends the user's other
sessions, so ``session_id`` can always name the session that started the flow; existing states keep false.

Revision ID: 3f7a9c1e5b82
Revises: c91ac2dad0f0
Create Date: 2026-11-09 00:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "3f7a9c1e5b82"
down_revision: str | None = "c91ac2dad0f0"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABLE = "account_security_generations"
_STATES = "oauth_states"
_STATE_COLUMN = "security_generation"
_ENDS_OTHERS_COLUMN = "ends_other_sessions"
_SESSION_COLUMN = "session_id"


def upgrade() -> None:
    """Create ``account_security_generations`` and add the OAuth-state columns."""
    op.create_table(
        _TABLE,
        sa.Column("user_id", sa.Integer(), nullable=False, comment="User the generation belongs to"),
        sa.Column(
            "generation",
            sa.Integer(),
            server_default=sa.text("0"),
            nullable=False,
            comment="Counter advanced by every security change; a pending proof records the value it was created under",
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
            comment="When the generation last changed",
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("user_id"),
    )
    op.add_column(
        _STATES,
        sa.Column(
            _STATE_COLUMN,
            sa.Integer(),
            nullable=True,
            comment="Account security generation the flow was started under; it is redeemed only while still current",
        ),
    )
    op.add_column(
        _STATES,
        sa.Column(
            _ENDS_OTHERS_COLUMN,
            sa.Boolean(),
            server_default=sa.false(),
            nullable=False,
            comment="Whether the callback of a link ends the user's other sessions",
        ),
    )
    op.alter_column(
        _STATES,
        _SESSION_COLUMN,
        existing_type=sa.String(length=36),
        existing_nullable=True,
        comment="Session that started a link or step-up flow",
        existing_comment="Session that started a step-up flow, or a link that ends the user's other sessions",
    )


def downgrade() -> None:
    """Drop the OAuth-state columns and ``account_security_generations``."""
    op.alter_column(
        _STATES,
        _SESSION_COLUMN,
        existing_type=sa.String(length=36),
        existing_nullable=True,
        comment="Session that started a step-up flow, or a link that ends the user's other sessions",
        existing_comment="Session that started a link or step-up flow",
    )
    op.drop_column(_STATES, _ENDS_OTHERS_COLUMN)
    op.drop_column(_STATES, _STATE_COLUMN)
    op.drop_table(_TABLE)
