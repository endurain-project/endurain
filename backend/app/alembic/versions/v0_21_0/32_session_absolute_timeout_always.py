"""32: always apply the absolute session timeout

``session_idle_timeout_enabled`` now turns only the idle timeout on or off; the absolute timeout always applies and
defaults to 720 hours (30 days). An install that never enabled the timeouts never enforced its stored absolute
timeout, so one left at the old 24-hour default moves to 720 hours instead of suddenly ending sessions after a day.
The idle timeout of such an install is at most 24 hours (the absolute timeout cannot be shorter), so 720 keeps the
check constraint.

Revision ID: 4b7e2c9d1a63
Revises: 6d3a8f1c5e92
Create Date: 2026-10-31 10:00:00

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "4b7e2c9d1a63"
down_revision: str | None = "6d3a8f1c5e92"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_NEW_COMMENT = "Enforce the session idle timeout (true - yes, false - no); the absolute timeout always applies"
_OLD_COMMENT = "Enforce session idle and absolute timeouts (true - yes, false - no)"


def upgrade() -> None:
    """Default the absolute timeout to 720 hours and lift the unenforced 24-hour value on installs without timeouts."""
    op.alter_column(
        "server_settings",
        "session_absolute_timeout_hours",
        existing_type=sa.Integer(),
        existing_nullable=False,
        server_default=sa.text("720"),
    )
    op.alter_column(
        "server_settings",
        "session_idle_timeout_enabled",
        existing_type=sa.Boolean(),
        existing_nullable=False,
        existing_server_default=sa.text("false"),
        comment=_NEW_COMMENT,
    )
    op.execute(
        "UPDATE server_settings SET session_absolute_timeout_hours = 720 "
        "WHERE session_idle_timeout_enabled = false AND session_absolute_timeout_hours = 24"
    )


def downgrade() -> None:
    """Restore the 24-hour default and the old comment. The raised absolute timeouts are not restored."""
    op.alter_column(
        "server_settings",
        "session_idle_timeout_enabled",
        existing_type=sa.Boolean(),
        existing_nullable=False,
        existing_server_default=sa.text("false"),
        comment=_OLD_COMMENT,
    )
    op.alter_column(
        "server_settings",
        "session_absolute_timeout_hours",
        existing_type=sa.Integer(),
        existing_nullable=False,
        server_default=sa.text("24"),
    )
