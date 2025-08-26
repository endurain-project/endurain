"""Add MFA support fields to users table

Revision ID: add_mfa_support
Revises: 2fb0ae78dea9
Create Date: 2025-01-26 12:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "add_mfa_support"
down_revision: Union[str, None] = "2fb0ae78dea9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add MFA fields to users table
    op.add_column('users', sa.Column('mfa_enabled', sa.Integer(), nullable=False, default=0, comment='Whether MFA is enabled for this user (0 - disabled, 1 - enabled)'))
    op.add_column('users', sa.Column('mfa_secret', sa.String(length=64), nullable=True, comment='User MFA secret for TOTP generation (encrypted at rest)'))


def downgrade() -> None:
    # Remove MFA fields from users table
    op.drop_column('users', 'mfa_secret')
    op.drop_column('users', 'mfa_enabled')