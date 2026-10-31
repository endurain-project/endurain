"""10: enforce the settings rules the application relies on

The absolute session timeout is never below the idle timeout, and the geocoding rate limit is
within the range the settings schema accepts, so a row written without going through the schema
cannot break every read of the settings.

Revision ID: f4c8a2e6b7d1
Revises: e3b7a5d1c968
Create Date: 2026-10-27 00:00:00.000000

"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "f4c8a2e6b7d1"
down_revision: str | None = "e3b7a5d1c968"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add the two check constraints."""
    op.create_check_constraint(
        "session_absolute_not_below_idle_check",
        "server_settings",
        "session_absolute_timeout_hours >= session_idle_timeout_hours",
    )
    op.create_check_constraint(
        "geocoding_rate_limit_check", "server_settings", "geocoding_rate_limit BETWEEN 0 AND 100"
    )


def downgrade() -> None:
    """Drop the two check constraints."""
    op.drop_constraint("geocoding_rate_limit_check", "server_settings", type_="check")
    op.drop_constraint("session_absolute_not_below_idle_check", "server_settings", type_="check")
