"""76: index the one-time token hashes and make them unique

Every unauthenticated password-reset and sign-up validation or confirmation looks a token up by its hash, which
scanned the whole table, and nothing enforced that a hash identifies one row, which the redelivery of a mail event
relies on. The hash columns now carry a unique index. A hash stored twice by older code (two concurrent deliveries
of one event) names one link, so the earliest row (by creation time, then id) is kept and the others are deleted.

Revision ID: f76d4b8e1c35
Revises: e75c9a3d7b24
Create Date: 2026-11-10 19:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "f76d4b8e1c35"
down_revision: str | None = "e75c9a3d7b24"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABLES = ("password_reset_tokens", "sign_up_tokens")


def upgrade() -> None:
    """Delete the later rows of any repeated hash, then create the unique indexes."""
    for name in _TABLES:
        tokens = sa.table(name, sa.column("id"), sa.column("token_hash"), sa.column("created_at"))
        earlier = tokens.alias("earlier")
        has_earlier_twin = (
            sa.select(sa.literal(1))
            .where(
                earlier.c.token_hash == tokens.c.token_hash,
                sa.or_(
                    earlier.c.created_at < tokens.c.created_at,
                    sa.and_(earlier.c.created_at == tokens.c.created_at, earlier.c.id < tokens.c.id),
                ),
            )
            .exists()
        )
        op.execute(tokens.delete().where(has_earlier_twin))
        op.create_index(op.f(f"ix_{name}_token_hash"), name, ["token_hash"], unique=True)


def downgrade() -> None:
    """Drop the unique indexes."""
    for table in reversed(_TABLES):
        op.drop_index(op.f(f"ix_{table}_token_hash"), table_name=table)
