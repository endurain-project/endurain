"""v0.15.0 migration

Revision ID: 3c4d5e6f7a8b
Revises: 86b2e24e227e
Create Date: 2025-01-01 12:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "3c4d5e6f7a8b"
down_revision: Union[str, None] = "86b2e24e227e"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add new columns to server_settings table
    op.add_column(
        "server_settings",
        sa.Column(
            "signup_enabled",
            sa.Boolean(),
            nullable=True,
            default=False,
            comment="Allow user sign-up registration (true - yes, false - no)",
        ),
    )
    op.execute(
        """
        UPDATE server_settings
        SET signup_enabled = false
        WHERE signup_enabled IS NULL;
    """
    )
    op.alter_column(
        "server_settings",
        "signup_enabled",
        nullable=False,
        comment="Allow user sign-up registration (true - yes, false - no)",
        existing_type=sa.Boolean(),
    )
    op.add_column(
        "server_settings",
        sa.Column(
            "signup_require_admin_approval",
            sa.Boolean(),
            nullable=True,
            default=True,
            comment="Require admin approval for new sign-ups (true - yes, false - no)",
        ),
    )
    op.execute(
        """
        UPDATE server_settings
        SET signup_require_admin_approval = false
        WHERE signup_require_admin_approval IS NULL;
    """
    )
    op.alter_column(
        "server_settings",
        "signup_require_admin_approval",
        nullable=False,
        comment="Require admin approval for new sign-ups (true - yes, false - no)",
        existing_type=sa.Boolean(),
    )
    op.add_column(
        "server_settings",
        sa.Column(
            "signup_require_email_verification",
            sa.Boolean(),
            nullable=True,
            default=True,
            comment="Require email verification for new sign-ups (true - yes, false - no)",
        ),
    )
    op.execute(
        """
        UPDATE server_settings
        SET signup_require_email_verification = false
        WHERE signup_require_email_verification IS NULL;
    """
    )
    op.alter_column(
        "server_settings",
        "signup_require_email_verification",
        nullable=False,
        comment="Require email verification for new sign-ups (true - yes, false - no)",
        existing_type=sa.Boolean(),
    )
    # Add new columns to users table
    op.add_column(
        "users",
        sa.Column(
            "email_verified",
            sa.Boolean(),
            nullable=True,
            default=False,
            comment="Whether the user's email address has been verified (true - yes, false - no)",
        ),
    )
    op.execute(
        """
        UPDATE users
        SET email_verified = true
        WHERE email_verified IS NULL;
    """
    )
    op.alter_column(
        "users",
        "email_verified",
        nullable=False,
        comment="Whether the user's email address has been verified (true - yes, false - no)",
        existing_type=sa.Boolean(),
    )
    op.add_column(
        "users",
        sa.Column(
            "email_verification_token",
            sa.String(length=255),
            nullable=True,
            comment="Token for email verification",
        ),
    )
    op.add_column(
        "users",
        sa.Column(
            "pending_admin_approval",
            sa.Boolean(),
            nullable=True,
            default=False,
            comment="Whether the user is pending admin approval for activation (true - yes, false - no)",
        ),
    )
    op.execute(
        """
        UPDATE users
        SET pending_admin_approval = false
        WHERE pending_admin_approval IS NULL;
    """
    )
    op.alter_column(
        "users",
        "pending_admin_approval",
        nullable=False,
        comment="Whether the user is pending admin approval for activation (true - yes, false - no)",
        existing_type=sa.Boolean(),
    )


def downgrade() -> None:
    # Remove columns from users table
    op.drop_column("users", "pending_admin_approval")
    op.drop_column("users", "email_verification_token")
    op.drop_column("users", "email_verified")

    # Remove columns from server_settings table
    op.drop_column("server_settings", "signup_require_email_verification")
    op.drop_column("server_settings", "signup_require_admin_approval")
    op.drop_column("server_settings", "signup_enabled")
