"""65: session idle timeout on (72 hours) for new installs

The idle timeout shipped off at 1 hour. This sets it to on at 72 hours on the single ``server_settings`` row, but
only when the ``users`` table is empty and both idle columns still hold the shipped values (false and 1). A fresh
install runs its migrations before its first account exists, so only new installs change; an existing install has
accounts and keeps its setting. The one harmless edge: an install upgraded before any account was ever created is
treated as new. Column server defaults and model defaults stay false and 1, because the row already exists and the
defaults only apply to rows inserted later. The deprecated ``SESSION_IDLE_TIMEOUT_*`` environment variables are
imported at startup, after migrations, and still win when set.

Revision ID: e65a3c4d5f6b
Revises: d64f2b3c4e5a
Create Date: 2026-11-08 13:00:00

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "e65a3c4d5f6b"
down_revision: str | None = "d64f2b3c4e5a"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Turn the idle timeout on at 72 hours when no account exists and the shipped values are untouched."""
    op.execute(
        sa.text(
            "UPDATE server_settings SET session_idle_timeout_enabled = :enabled, session_idle_timeout_hours = 72 "
            "WHERE id = 1 AND session_idle_timeout_enabled = :disabled AND session_idle_timeout_hours = 1 "
            "AND NOT EXISTS (SELECT 1 FROM users)"
        ).bindparams(
            sa.bindparam("enabled", True, type_=sa.Boolean()), sa.bindparam("disabled", False, type_=sa.Boolean())
        )
    )


def downgrade() -> None:
    """Restore the shipped values when the row still holds exactly what the upgrade set.

    Whether the install was new is not knowable later, so a row at true and 72 is reverted; an administrator who
    chose exactly those values loses nothing functional beyond returning to the previous release's default.
    """
    op.execute(
        sa.text(
            "UPDATE server_settings SET session_idle_timeout_enabled = :disabled, session_idle_timeout_hours = 1 "
            "WHERE id = 1 AND session_idle_timeout_enabled = :enabled AND session_idle_timeout_hours = 72"
        ).bindparams(
            sa.bindparam("enabled", True, type_=sa.Boolean()), sa.bindparam("disabled", False, type_=sa.Boolean())
        )
    )
