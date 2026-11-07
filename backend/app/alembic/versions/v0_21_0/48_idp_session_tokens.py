"""48: keep identity-provider tokens per session

Each Endurain session that signed in through an identity provider now has a row in ``idp_session_tokens``,
holding the refresh token that sign-in was issued, so a session is refreshed and revoked at the provider on
its own. The link's three token columns are dropped: a token stored there cannot be tied to a session and is
discarded, and the sessions open today keep working until they expire, without identity-provider refresh. The
downgrade restores the empty columns and drops the table.

Revision ID: c9f2d6a3e851
Revises: b4c8e1f7a362
Create Date: 2026-11-05 00:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c9f2d6a3e851"
down_revision: str | None = "b4c8e1f7a362"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABLE = "idp_session_tokens"
_LINKS = "users_identity_providers"
_IDP_INDEX = "ix_idp_session_tokens_idp_id"
_USER_INDEX = "ix_idp_session_tokens_user_id"


def upgrade() -> None:
    """Create the per-session token table and drop the link's token columns."""
    op.create_table(
        _TABLE,
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column(
            "session_id",
            sa.String(length=36),
            nullable=False,
            comment="Endurain session the sign-in created; no foreign key, so the token outlives the session row",
        ),
        sa.Column("user_id", sa.Integer(), nullable=False, comment="User ID"),
        sa.Column("idp_id", sa.Integer(), nullable=False, comment="Identity Provider ID"),
        sa.Column("refresh_token", sa.Text(), nullable=True, comment="Encrypted refresh token"),
        sa.Column(
            "access_token_expires_at",
            sa.DateTime(timezone=True),
            nullable=True,
            comment="Access token expiry time",
        ),
        sa.Column(
            "refresh_token_updated_at",
            sa.DateTime(timezone=True),
            nullable=True,
            comment="Last refresh token update",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
            comment="When the session signed in through the provider",
        ),
        sa.ForeignKeyConstraint(["idp_id"], ["identity_providers.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("session_id"),
    )
    op.create_index(_IDP_INDEX, _TABLE, ["idp_id"], unique=False)
    op.create_index(_USER_INDEX, _TABLE, ["user_id"], unique=False)
    op.drop_column(_LINKS, "idp_refresh_token_updated_at")
    op.drop_column(_LINKS, "idp_access_token_expires_at")
    op.drop_column(_LINKS, "idp_refresh_token")


def downgrade() -> None:
    """Restore the link's empty token columns and drop the per-session token table."""
    op.add_column(_LINKS, sa.Column("idp_refresh_token", sa.Text(), nullable=True, comment="Encrypted refresh token"))
    op.add_column(
        _LINKS,
        sa.Column(
            "idp_access_token_expires_at",
            sa.DateTime(timezone=True),
            nullable=True,
            comment="Access token expiry time",
        ),
    )
    op.add_column(
        _LINKS,
        sa.Column(
            "idp_refresh_token_updated_at",
            sa.DateTime(timezone=True),
            nullable=True,
            comment="Last refresh token update",
        ),
    )
    op.drop_index(_USER_INDEX, table_name=_TABLE)
    op.drop_index(_IDP_INDEX, table_name=_TABLE)
    op.drop_table(_TABLE)
