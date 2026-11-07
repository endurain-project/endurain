"""5: store the mail server settings in the database

Creates the singleton ``mail_settings`` table the admin UI edits, with its row
inserted so every install has one. Mail starts disabled (no host); an install that
sets the ``SMTP_*`` variables has them imported on the next API start.

Revision ID: 4b9d6e2a7c13
Revises: e3a7c91f5d28
Create Date: 2026-10-22 00:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "4b9d6e2a7c13"
down_revision: str | None = "e3a7c91f5d28"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create the mail_settings table and its singleton row."""
    op.create_table(
        "mail_settings",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("host", sa.String(length=253), nullable=True, comment="Mail server hostname (NULL - mail disabled)"),
        sa.Column("port", sa.Integer(), server_default=sa.text("587"), nullable=False, comment="Mail server port"),
        sa.Column(
            "security",
            sa.String(length=10),
            server_default="starttls",
            nullable=False,
            comment="Connection security (starttls, ssl, none)",
        ),
        sa.Column("username", sa.String(length=320), nullable=True, comment="Mail server authentication username"),
        sa.Column(
            "password",
            sa.String(length=512),
            nullable=True,
            comment="Mail server authentication password (encrypted)",
        ),
        sa.Column(
            "from_address",
            sa.String(length=320),
            nullable=True,
            comment="Sender address (NULL - the username is used)",
        ),
        sa.CheckConstraint("id = 1", name="mail_settings_single_row_check"),
        sa.CheckConstraint("security IN ('starttls', 'ssl', 'none')", name="mail_settings_security_check"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.execute(sa.text("INSERT INTO mail_settings (id) VALUES (1)"))


def downgrade() -> None:
    """Drop the mail_settings table."""
    op.drop_table("mail_settings")
