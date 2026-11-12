"""84: constrain users.access_type to the two known access types

Scope derivation fails closed on an access type it does not know, so the column only accepts ``regular`` and
``admin``. Every row written since revision 0.17.0 holds one of the two; the constraint creation fails on the
upgrade if a row holds anything else, rather than leaving an account no scope can be derived for.

Revision ID: b84e9f3a6c25
Revises: a83d7e2c5f19
Create Date: 2026-11-12 02:00:00.000000

"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "b84e9f3a6c25"
down_revision: str | None = "a83d7e2c5f19"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_CONSTRAINT = "ck_users_access_type"


def upgrade() -> None:
    """Add the check that limits ``users.access_type`` to ``regular`` and ``admin``."""
    op.create_check_constraint(_CONSTRAINT, "users", "access_type IN ('regular', 'admin')")


def downgrade() -> None:
    """Drop the access type check."""
    op.drop_constraint(_CONSTRAINT, "users", type_="check")
