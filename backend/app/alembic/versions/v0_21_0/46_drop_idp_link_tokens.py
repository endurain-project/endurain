"""46: drop the identity-provider link tokens

Linking an identity provider now starts from an authenticated ``POST``, so the one-time link tokens and their
table are gone. The downgrade recreates the empty table.

Revision ID: d2b6c8e4f193
Revises: c7e1f3a9d245
Create Date: 2026-11-05 00:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "d2b6c8e4f193"
down_revision: str | None = "c7e1f3a9d245"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Drop the link-token table and its indexes."""
    op.drop_index(op.f("ix_idp_link_tokens_user_id"), table_name="idp_link_tokens")
    op.drop_index(op.f("ix_idp_link_tokens_token_hash"), table_name="idp_link_tokens")
    op.drop_index(op.f("ix_idp_link_tokens_idp_id"), table_name="idp_link_tokens")
    op.drop_index(op.f("ix_idp_link_tokens_id"), table_name="idp_link_tokens")
    op.drop_index(op.f("ix_idp_link_tokens_expires_at"), table_name="idp_link_tokens")
    op.drop_table("idp_link_tokens")


def downgrade() -> None:
    """Recreate the empty link-token table with its indexes."""
    op.create_table(
        "idp_link_tokens",
        sa.Column("id", sa.String(length=36), nullable=False, comment="Opaque row identifier, not the link token"),
        sa.Column(
            "token_hash",
            sa.String(length=64),
            nullable=False,
            comment="SHA-256 hash of the one-time link token",
        ),
        sa.Column("user_id", sa.Integer(), nullable=False, comment="User ID linking the identity provider"),
        sa.Column("idp_id", sa.Integer(), nullable=False, comment="Identity provider ID being linked"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
            comment="Token creation timestamp",
        ),
        sa.Column(
            "expires_at",
            sa.DateTime(timezone=True),
            nullable=False,
            comment="Token expiry at 60 seconds (cleanup marker)",
        ),
        sa.Column(
            "used",
            sa.Boolean(),
            nullable=False,
            comment="Single-use flag (False - unused, True - used)",
        ),
        sa.Column("ip_address", sa.String(length=45), nullable=True, comment="Client IP address (IPv6 max length)"),
        sa.ForeignKeyConstraint(["idp_id"], ["identity_providers.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_idp_link_tokens_expires_at"), "idp_link_tokens", ["expires_at"], unique=False)
    op.create_index(op.f("ix_idp_link_tokens_id"), "idp_link_tokens", ["id"], unique=False)
    op.create_index(op.f("ix_idp_link_tokens_idp_id"), "idp_link_tokens", ["idp_id"], unique=False)
    op.create_index(op.f("ix_idp_link_tokens_token_hash"), "idp_link_tokens", ["token_hash"], unique=True)
    op.create_index(op.f("ix_idp_link_tokens_user_id"), "idp_link_tokens", ["user_id"], unique=False)
