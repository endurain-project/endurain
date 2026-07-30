"""12: register the activity media storage-key data migration

Revision ID: b3c4d5e6f7a8
Revises: 8c3d9f21e64b
Create Date: 2026-07-28 00:00:00.000000

"""

from collections.abc import Sequence

from alembic import op

revision: str = "b3c4d5e6f7a8"
down_revision: str | None = "8c3d9f21e64b"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Register the activity media storage-key data migration."""
    op.execute(
        """
    INSERT INTO migrations (id, name, description, executed) VALUES
    (9, 'v0.20.0', 'Rewrite activity media paths to storage keys', false);
    """
    )


def downgrade() -> None:
    """Remove the migration registration."""
    op.execute("DELETE FROM migrations WHERE id = 9;")
