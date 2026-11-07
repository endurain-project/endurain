"""42: register the image-metadata strip data migration

Revision ID: f2c6a9d4b871
Revises: d4b8e1a6c735
Create Date: 2026-11-05 00:00:00.000000

"""

from collections.abc import Sequence

from alembic import op

revision: str = "f2c6a9d4b871"
down_revision: str | None = "d4b8e1a6c735"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Register the image-metadata strip data migration."""
    op.execute(
        """
    INSERT INTO migrations (id, name, description, executed) VALUES
    (12, 'v0.21.0', 'Strip metadata from stored images and cap profile photos at 512 px', false);
    """
    )


def downgrade() -> None:
    """Remove the migration registration."""
    op.execute("DELETE FROM migrations WHERE id = 12;")
