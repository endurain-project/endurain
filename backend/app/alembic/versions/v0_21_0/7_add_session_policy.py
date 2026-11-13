"""7: store the session and token policy in the database

Adds the session timeout and token lifetime columns to ``server_settings``. The server
defaults equal the defaults of the ``SESSION_*``, ``ACCESS_TOKEN_EXPIRE_MINUTES`` and
``REFRESH_TOKEN_EXPIRE_DAYS`` variables; an install that sets them has them imported on
the next API start.

Revision ID: b5e8d2c4a916
Revises: 9c3e1f7a5d82
Create Date: 2026-10-24 00:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "b5e8d2c4a916"
down_revision: str | None = "9c3e1f7a5d82"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_BOUNDED_COLUMNS: tuple[tuple[str, int, str, int, str], ...] = (
    ("session_idle_timeout_hours", 1, "Hours of inactivity after which a session ends", 8760, "1"),
    ("session_absolute_timeout_hours", 24, "Hours after which a session ends whatever its activity", 8760, "1"),
    ("access_token_expire_minutes", 15, "Access token lifetime in minutes", 1440, "1"),
    ("refresh_token_expire_days", 7, "Refresh token lifetime in days", 365, "1"),
)


def upgrade() -> None:
    """Add the session policy columns and their range check constraints."""
    op.add_column(
        "server_settings",
        sa.Column(
            "session_idle_timeout_enabled",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
            comment="Enforce session idle and absolute timeouts (true - yes, false - no)",
        ),
    )
    for name, default, comment, upper, lower in _BOUNDED_COLUMNS:
        op.add_column(
            "server_settings",
            sa.Column(name, sa.Integer(), server_default=sa.text(str(default)), nullable=False, comment=comment),
        )
        op.create_check_constraint(f"{name}_check", "server_settings", f"{name} BETWEEN {lower} AND {upper}")


def downgrade() -> None:
    """Drop the session policy columns."""
    for name, *_ in reversed(_BOUNDED_COLUMNS):
        op.drop_constraint(f"{name}_check", "server_settings", type_="check")
        op.drop_column("server_settings", name)
    op.drop_column("server_settings", "session_idle_timeout_enabled")
