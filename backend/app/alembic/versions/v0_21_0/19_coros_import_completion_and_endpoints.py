"""19: track complete COROS FIT imports and the advertised OAuth endpoints

Revision ID: a2d4f6b8c0e1
Revises: f3a7c1e9b2d4
Create Date: 2026-11-22 00:00:00.000000

A COROS FIT file can contain several sessions, and ingestion commits each one
separately. The completion marker is written only after every session of a file
was stored, so a partial import is retried instead of being treated as complete.

The token and revocation endpoints are stored as discovered, because COROS may
advertise paths other than the ones under its issuer. A missing revocation
endpoint means revocation is skipped instead of posting to a guessed path.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a2d4f6b8c0e1"
down_revision: str | None = "f3a7c1e9b2d4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add the completion marker table and the discovered OAuth endpoints."""
    op.add_column(
        "coros_integrations",
        sa.Column(
            "token_endpoint",
            sa.String(length=500),
            nullable=True,
            comment="COROS OAuth token endpoint advertised during discovery",
        ),
    )
    op.add_column(
        "coros_integrations",
        sa.Column(
            "revocation_endpoint",
            sa.String(length=500),
            nullable=True,
            comment="COROS OAuth revocation endpoint advertised during discovery",
        ),
    )
    op.create_table(
        "coros_imported_activities",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("label_id", sa.String(length=64), nullable=False, comment="COROS activity identifier"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
            comment="When the complete FIT file was imported",
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "label_id", name="uq_coros_imported_activities_user_label"),
    )
    op.create_index("ix_coros_imported_activities_user_id", "coros_imported_activities", ["user_id"])


def downgrade() -> None:
    """Drop the completion marker table and the discovered OAuth endpoints."""
    op.drop_index("ix_coros_imported_activities_user_id", table_name="coros_imported_activities")
    op.drop_table("coros_imported_activities")
    op.drop_column("coros_integrations", "revocation_endpoint")
    op.drop_column("coros_integrations", "token_endpoint")
