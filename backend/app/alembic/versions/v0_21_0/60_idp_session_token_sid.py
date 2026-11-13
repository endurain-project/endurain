"""60: keep the provider session id of each identity-provider sign-in

OpenID Connect Back-Channel Logout 1.0 names the provider session to end with the ``sid`` the provider put in the
ID token at sign-in, so the sign-in keeps it, indexed for the lookup by provider and ``sid``. Existing sign-ins hold
none: a logout token that names only their ``sid`` matches nothing, and one that names the user's ``sub`` still
ends them.

Revision ID: c09e5b7d2f14
Revises: b12d4f6a8e30
Create Date: 2026-11-07 14:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c09e5b7d2f14"
down_revision: str | None = "b12d4f6a8e30"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABLE = "idp_session_tokens"
_SID_INDEX = "ix_idp_session_tokens_idp_id_idp_sid"


def upgrade() -> None:
    """Add the column, empty for every existing sign-in, and its index."""
    op.add_column(
        _TABLE,
        sa.Column(
            "idp_sid",
            sa.String(length=255),
            nullable=True,
            comment="Provider session id (sid) of the verified ID token, named by back-channel logout",
        ),
    )
    op.create_index(_SID_INDEX, _TABLE, ["idp_id", "idp_sid"], unique=False)


def downgrade() -> None:
    """Drop the index and the column."""
    op.drop_index(_SID_INDEX, table_name=_TABLE)
    op.drop_column(_TABLE, "idp_sid")
