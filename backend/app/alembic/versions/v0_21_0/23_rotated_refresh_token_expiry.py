"""23: keep a rotated refresh-token record until its own token expires

Reuse detection needs a rotated token's record for as long as that token could still be presented.
The purge used the deployment's default refresh-token lifetime, so with a longer lifetime set in the
server settings the record went while the token was still valid and a replay was no longer recognised
as theft. Each record now carries its token's expiry and is purged after it.

A token was issued before it was rotated, so ``rotated_at`` plus the configured lifetime is never
earlier than its real expiry; existing records are filled with that bound, or with the longest allowed
lifetime (365 days) when no settings row exists.

Revision ID: 3b7d9e1f5a20
Revises: 7e2c5a9f4b18
Create Date: 2026-10-29 00:00:00

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "3b7d9e1f5a20"
down_revision: str | None = "7e2c5a9f4b18"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_INDEX = "ix_rotated_refresh_tokens_refresh_token_exp"


def upgrade() -> None:
    """Add, backfill and index the rotated token's expiry."""
    op.add_column(
        "rotated_refresh_tokens",
        sa.Column(
            "refresh_token_exp",
            sa.DateTime(timezone=True),
            nullable=True,
            comment="Expiry of the rotated refresh token; the record is purged after it",
        ),
    )
    op.execute(
        "UPDATE rotated_refresh_tokens SET refresh_token_exp = rotated_at + make_interval(days => COALESCE("
        "(SELECT refresh_token_expire_days FROM server_settings WHERE id = 1), 365))"
    )
    op.alter_column(
        "rotated_refresh_tokens", "refresh_token_exp", existing_type=sa.DateTime(timezone=True), nullable=False
    )
    op.create_index(_INDEX, "rotated_refresh_tokens", ["refresh_token_exp"])


def downgrade() -> None:
    """Drop the rotated token's expiry."""
    op.drop_index(_INDEX, table_name="rotated_refresh_tokens")
    op.drop_column("rotated_refresh_tokens", "refresh_token_exp")
