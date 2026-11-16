"""29: add the COROS integration and its activity identifier

Revision ID: f3a7c1e9b2d4
Revises: c91ac2dad0f0
Create Date: 2026-11-16 00:00:00.000000

COROS is connected per user through its official MCP OAuth server. Tokens and
the short-lived PKCE verifier are Fernet-encrypted, so the connection table has
no plaintext credential. Activities are deduplicated by a salted COROS id, and
an activity COROS cannot provide a FIT file for is recorded once instead of
being retried on every hourly sync.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "f3a7c1e9b2d4"
down_revision: str | None = "c91ac2dad0f0"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create the COROS tables and add the activity identifier column."""
    op.add_column(
        "activities",
        sa.Column(
            "coros_activity_id",
            sa.String(length=64),
            nullable=True,
            comment="COROS activity ID",
        ),
    )
    op.create_index(
        "ix_activities_user_coros_activity_id",
        "activities",
        ["user_id", "coros_activity_id"],
    )
    op.create_table(
        "coros_integrations",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("mcp_url", sa.String(length=255), nullable=True, comment="Regional COROS MCP endpoint"),
        sa.Column("issuer", sa.String(length=255), nullable=True, comment="COROS OAuth issuer"),
        sa.Column(
            "redirect_uri", sa.String(length=500), nullable=True, comment="OAuth callback URI registered with COROS"
        ),
        sa.Column("scope", sa.String(length=255), nullable=True, comment="Granted OAuth scopes"),
        sa.Column(
            "client_id", sa.String(length=255), nullable=True, comment="Dynamically registered public OAuth client ID"
        ),
        sa.Column(
            "client_secret",
            sa.Text(),
            nullable=True,
            comment="COROS OAuth client secret encrypted at rest with Fernet key",
        ),
        sa.Column("state", sa.String(length=128), nullable=True, comment="Temporary OAuth state for the link process"),
        sa.Column("code_verifier", sa.Text(), nullable=True, comment="PKCE verifier encrypted at rest with Fernet key"),
        sa.Column(
            "state_expires_at", sa.DateTime(timezone=True), nullable=True, comment="Expiry of the pending OAuth state"
        ),
        sa.Column(
            "access_token", sa.Text(), nullable=True, comment="COROS access token encrypted at rest with Fernet key"
        ),
        sa.Column(
            "refresh_token", sa.Text(), nullable=True, comment="COROS refresh token encrypted at rest with Fernet key"
        ),
        sa.Column(
            "token_expires_at", sa.DateTime(timezone=True), nullable=True, comment="COROS access token expiration date"
        ),
        sa.Column(
            "refresh_token_expires_at",
            sa.DateTime(timezone=True),
            nullable=True,
            comment="COROS refresh token expiration date",
        ),
        sa.Column("last_sync_at", sa.DateTime(timezone=True), nullable=True, comment="Last COROS sync attempt"),
        sa.Column(
            "last_sync_status",
            sa.String(length=32),
            nullable=False,
            server_default="never",
            comment="Outcome of the most recent COROS sync",
        ),
        sa.Column(
            "last_sync_error",
            sa.String(length=64),
            nullable=True,
            comment="Sanitized reason for the most recent failed COROS sync",
        ),
        sa.Column(
            "last_sync_activity_count",
            sa.Integer(),
            nullable=False,
            server_default="0",
            comment="Activities stored by the most recent successful COROS sync",
        ),
        sa.Column(
            "fit_download_date", sa.Date(), nullable=True, comment="UTC date the COROS FIT download counter belongs to"
        ),
        sa.Column(
            "fit_download_count",
            sa.Integer(),
            nullable=False,
            server_default="0",
            comment="COROS FIT downloads already requested on fit_download_date",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
            comment="Row creation date",
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
            comment="Last row update date",
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_coros_integrations_user_id", "coros_integrations", ["user_id"], unique=True)
    op.create_index("ix_coros_integrations_state", "coros_integrations", ["state"], unique=True)

    op.create_table(
        "coros_skipped_activities",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("label_id", sa.String(length=64), nullable=False, comment="COROS activity identifier"),
        sa.Column("reason", sa.String(length=32), nullable=False, comment="Why the COROS activity was skipped"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
            comment="When the activity was first skipped",
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "label_id", name="uq_coros_skipped_activities_user_label"),
    )
    op.create_index("ix_coros_skipped_activities_user_id", "coros_skipped_activities", ["user_id"])


def downgrade() -> None:
    """Drop the COROS tables and activity identifier column."""
    op.drop_index("ix_coros_skipped_activities_user_id", table_name="coros_skipped_activities")
    op.drop_table("coros_skipped_activities")
    op.drop_index("ix_coros_integrations_state", table_name="coros_integrations")
    op.drop_index("ix_coros_integrations_user_id", table_name="coros_integrations")
    op.drop_table("coros_integrations")
    op.drop_index("ix_activities_user_coros_activity_id", table_name="activities")
    op.drop_column("activities", "coros_activity_id")
