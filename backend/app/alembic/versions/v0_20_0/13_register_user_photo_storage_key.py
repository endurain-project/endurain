"""13: register the user photo storage-key data migration

Revision ID: d4e5f6a7b8c9
Revises: b3c4d5e6f7a8
Create Date: 2026-07-29 00:00:00.000000

"""

from collections.abc import Sequence

from alembic import op

revision: str = "d4e5f6a7b8c9"
down_revision: str | None = "b3c4d5e6f7a8"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Register the user photo storage-key data migration."""
    op.execute(
        """
    INSERT INTO migrations (id, name, description, executed) VALUES
    (10, 'v0.20.0', 'Rewrite user photo paths to storage keys', false);
    """
    )


def downgrade() -> None:
    """Remove the migration registration."""
    op.execute("DELETE FROM migrations WHERE id = 10;")
