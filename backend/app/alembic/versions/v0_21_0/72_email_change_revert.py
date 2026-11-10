"""72: keep an email change's "this wasn't me" link working for seven days

The link mailed to the previous address names the stored email change instead of the account's security generation,
so confirming the change no longer ends it. ``change_id`` identifies the change across the rows that re-issue its
confirmation link, ``revert_until`` ends its revert window and the row is kept until then, ``confirmed_at`` records
when a token was confirmed and ``reverted_at`` when the link was used.

Existing email-change rows become their own change with a window seven days after they were created. Rows that were
already used keep a null ``confirmed_at``, because a confirmed change cannot be told from a replaced one, so only a
change that is still pending at the upgrade can be cancelled with the link.

Revision ID: b72f5d0a3c81
Revises: a71e4c9d2b60
Create Date: 2026-11-10 15:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "b72f5d0a3c81"
down_revision: str | None = "a71e4c9d2b60"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABLE = "sign_up_tokens"
_CHANGE_INDEX = "ix_sign_up_tokens_change_id"


def upgrade() -> None:
    """Add the change, window, confirmation and revert columns and backfill the existing email-change rows."""
    op.add_column(
        _TABLE,
        sa.Column(
            "change_id",
            sa.String(length=64),
            nullable=True,
            comment="Identifier of the email change the token belongs to (email-change tokens only)",
        ),
    )
    op.add_column(
        _TABLE,
        sa.Column(
            "revert_until",
            sa.DateTime(timezone=True),
            nullable=True,
            comment="End of the email change's revert window (email-change tokens only)",
        ),
    )
    op.add_column(
        _TABLE,
        sa.Column(
            "confirmed_at",
            sa.DateTime(timezone=True),
            nullable=True,
            comment="When the token was confirmed, or the email change it records was applied",
        ),
    )
    op.add_column(
        _TABLE,
        sa.Column(
            "reverted_at",
            sa.DateTime(timezone=True),
            nullable=True,
            comment="When the email change's revert link was used (email-change tokens only)",
        ),
    )
    op.create_index(_CHANGE_INDEX, _TABLE, ["change_id"])
    op.execute(
        "UPDATE sign_up_tokens SET change_id = id, revert_until = created_at + INTERVAL '7 days' "
        "WHERE previous_email IS NOT NULL"
    )


def downgrade() -> None:
    """Drop the columns."""
    op.drop_index(_CHANGE_INDEX, table_name=_TABLE)
    op.drop_column(_TABLE, "reverted_at")
    op.drop_column(_TABLE, "confirmed_at")
    op.drop_column(_TABLE, "revert_until")
    op.drop_column(_TABLE, "change_id")
