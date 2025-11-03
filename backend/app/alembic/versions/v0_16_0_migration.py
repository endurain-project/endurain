"""v0.16.0 migration - Add max_heart_rate to users

Revision ID: 9d8e7f6a5b4c
Revises: 3c4d5e6f7a8b
Create Date: 2025-11-03 12:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "9d8e7f6a5b4c"
down_revision: Union[str, None] = "3c4d5e6f7a8b"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add max_heart_rate column to users table
    op.add_column(
        "users",
        sa.Column(
            "max_heart_rate",
            sa.Integer(),
            nullable=True,
            comment="User maximum heart rate (bpm)",
        ),
    )


def downgrade() -> None:
    # Remove max_heart_rate column from users table
    op.drop_column("users", "max_heart_rate")
