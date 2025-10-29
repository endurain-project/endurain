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
    op.add_column(
        "users",
        sa.Column(
            "active",
            sa.Boolean(),
            nullable=True,
            default=False,
            comment="Whether the user is active (true - yes, false - no)",
        ),
    )
    op.execute(
        """
        UPDATE users
        SET active = true
        WHERE is_active = 1;
        UPDATE users
        SET active = false
        WHERE is_active = 2;
    """
    )
    op.alter_column(
        "users",
        "active",
        nullable=False,
        comment="Whether the user is active (true - yes, false - no)",
        existing_type=sa.Boolean(),
    )
    op.drop_column("users", "is_active")
    # Add new columns to gear table
    op.add_column(
        "gear",
        sa.Column(
            "active",
            sa.Boolean(),
            nullable=True,
            default=True,
            comment="Whether the gear is active (true - yes, false - no)",
        ),
    )
    op.execute(
        """
        UPDATE gear
        SET active = true
        WHERE is_active = 1;
        UPDATE gear
        SET active = false
        WHERE is_active = 0;
    """
    )
    op.alter_column(
        "gear",
        "active",
        nullable=False,
        comment="Whether the gear is active (true - yes, false - no)",
        existing_type=sa.Boolean(),
    )
    op.drop_column("gear", "is_active")
    # Add new columns to gear component table
    op.add_column(
        "gear_components",
        sa.Column(
            "active",
            sa.Boolean(),
            nullable=True,
            default=True,
            comment="Whether the gear component is active (true - yes, false - no)",
        ),
    )
    op.execute(
        """
        UPDATE gear_components
        SET active = true
        WHERE is_active = true;
        UPDATE gear_components
        SET active = false
        WHERE is_active = false;
    """
    )
    op.alter_column(
        "gear_components",
        "active",
        nullable=False,
        comment="Whether the gear component is active (true - yes, false - no)",
        existing_type=sa.Boolean(),
    )
    op.drop_column("gear_components", "is_active")
    # Sign up tokens table
    op.create_table(
        "sign_up_tokens",
        sa.Column(
            "id",
            sa.String(length=64),
            nullable=False,
        ),
        sa.Column(
            "user_id",
            sa.Integer(),
            nullable=False,
            comment="User ID that the sign up token belongs to",
        ),
        sa.Column(
            "token_hash",
            sa.String(length=128),
            nullable=False,
            comment="Hashed sign up token",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=False,
            comment="Token creation date (datetime)",
        ),
        sa.Column(
            "expires_at",
            sa.DateTime(),
            nullable=False,
            comment="Token expiration date (datetime)",
        ),
        sa.Column(
            "used",
            sa.Boolean(),
            nullable=False,
            comment="Token usage status (False - unused, True - used)",
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_sign_up_tokens_user_id"),
        "sign_up_tokens",
        ["user_id"],
        unique=False,
    )
    # Add the new entry to the migrations table
    op.execute(
        """
    INSERT INTO migrations (id, name, description, executed) VALUES
    (6, 'v0.15.0', 'Lowercase user usernames', false);
    """
    )


def downgrade() -> None:
    # Remove the entry from the migrations table
    op.execute(
        """
    DELETE FROM migrations 
    WHERE id = 6;
    """
    )
    # Drop sign up tokens table
    op.drop_index(op.f("ix_sign_up_tokens_user_id"), table_name="sign_up_tokens")
    op.drop_table("sign_up_tokens")
    # Remove columns from gear_components table
    op.add_column(
        "gear_components",
        sa.Column(
            "is_active",
            sa.Boolean(),
            nullable=True,
            default=True,
            comment="Is gear component active",
        ),
    )
    op.execute(
        """
        UPDATE gear_components
        SET is_active = true
        WHERE active = true;
        UPDATE gear_components
        SET is_active = false
        WHERE active = false;
    """
    )
    op.alter_column(
        "gear_components",
        "is_active",
        nullable=False,
        comment="Is gear component active",
        existing_type=sa.Boolean(),
    )
    op.drop_column("gear_components", "active")
    # Remove columns from gear table
    op.add_column(
        "gear",
        sa.Column(
            "is_active",
            sa.Integer(),
            nullable=True,
            default=1,
            comment="Is gear active (0 - not active, 1 - active)",
        ),
    )
    op.execute(
        """
        UPDATE gear
        SET is_active = 1
        WHERE active = true;
        UPDATE gear
        SET is_active = 0
        WHERE active = false;
    """
    )
    op.alter_column(
        "gear",
        "is_active",
        nullable=False,
        comment="Is gear active (0 - not active, 1 - active)",
        existing_type=sa.Integer(),
    )
    op.drop_column("gear", "active")
    # Remove columns from users table
    op.add_column(
        "users",
        sa.Column(
            "is_active",
            sa.Integer(),
            nullable=True,
            default=1,
            comment="Is user active (1 - active, 2 - not active)",
        ),
    )
    op.execute(
        """
        UPDATE users
        SET is_active = 1
        WHERE active = true;
        UPDATE users
        SET is_active = 2
        WHERE active = false;
    """
    )
    op.alter_column(
        "users",
        "is_active",
        nullable=False,
        comment="Is user active (1 - active, 2 - not active)",
        existing_type=sa.Integer(),
    )
    op.drop_column("users", "active")
    op.drop_column("users", "pending_admin_approval")
    op.drop_column("users", "email_verified")

    # Remove columns from server_settings table
    op.drop_column("server_settings", "signup_require_email_verification")
    op.drop_column("server_settings", "signup_require_admin_approval")
    op.drop_column("server_settings", "signup_enabled")
