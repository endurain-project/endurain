"""10: register the thumbnail WebP + storage-key data migration

Revision ID: f4a5b6c7d8e9
Revises: e7f8a9b0c1d2
Create Date: 2026-07-09 00:00:00.000000

"""

from collections.abc import Sequence

from alembic import op

revision: str = "f4a5b6c7d8e9"
down_revision: str | None = "e7f8a9b0c1d2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Register the thumbnail WebP / storage-key data migration."""
    op.execute(
        """
    INSERT INTO migrations (id, name, description, executed) VALUES
    (8, 'v0.19.0', 'Re-encode legacy PNG thumbnails to WebP and store storage keys', false);
    """
    )


def downgrade() -> None:
    """Remove the migration registration."""
    op.execute("DELETE FROM migrations WHERE id = 8;")
