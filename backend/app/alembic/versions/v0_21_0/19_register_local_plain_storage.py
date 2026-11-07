"""19: register the local plain-storage data migration

Revision ID: e6a3b8d1f2c4
Revises: d5b8f1a3c7e2
Create Date: 2026-10-27 00:00:00.000000

"""

from collections.abc import Sequence

from alembic import op

revision: str = "e6a3b8d1f2c4"
down_revision: str | None = "d5b8f1a3c7e2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Register the local plain-storage data migration."""
    op.execute(
        """
    INSERT INTO migrations (id, name, description, executed) VALUES
    (11, 'v0.21.0', 'Move local storage objects into plain area paths', false);
    """
    )


def downgrade() -> None:
    """Remove the migration registration."""
    op.execute("DELETE FROM migrations WHERE id = 11;")
