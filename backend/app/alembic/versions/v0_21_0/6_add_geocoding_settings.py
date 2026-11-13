"""6: store the reverse-geocoding settings in the database

Adds the geocoding columns to ``server_settings``. The server defaults reproduce the
behaviour of an install without the ``REVERSE_GEO_*`` variables (Nominatim over HTTPS,
one request per second); an install that sets them has them imported on the next API start.

Revision ID: 9c3e1f7a5d82
Revises: 4b9d6e2a7c13
Create Date: 2026-10-23 00:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "9c3e1f7a5d82"
down_revision: str | None = "4b9d6e2a7c13"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add the geocoding columns and the service check constraint."""
    op.add_column(
        "server_settings",
        sa.Column(
            "geocoding_service",
            sa.String(length=20),
            server_default="nominatim",
            nullable=False,
            comment="Reverse-geocoding service (nominatim, photon, geocode)",
        ),
    )
    op.add_column(
        "server_settings",
        sa.Column(
            "geocoding_host",
            sa.String(length=253),
            nullable=True,
            comment="Host of the geocoding service (NULL - the service's default host)",
        ),
    )
    op.add_column(
        "server_settings",
        sa.Column(
            "geocoding_use_https",
            sa.Boolean(),
            server_default=sa.text("true"),
            nullable=False,
            comment="Address the geocoding host over HTTPS (true - yes, false - no)",
        ),
    )
    op.add_column(
        "server_settings",
        sa.Column(
            "geocoding_rate_limit",
            sa.Float(),
            server_default=sa.text("1.0"),
            nullable=False,
            comment="Maximum geocoding requests per second (0 disables throttling)",
        ),
    )
    op.add_column(
        "server_settings",
        sa.Column(
            "geocoding_api_key",
            sa.String(length=512),
            nullable=True,
            comment="API key encrypted for the geocoding service",
        ),
    )
    op.create_check_constraint(
        "geocoding_service_check",
        "server_settings",
        "geocoding_service IN ('nominatim', 'photon', 'geocode')",
    )


def downgrade() -> None:
    """Drop the geocoding columns."""
    op.drop_constraint("geocoding_service_check", "server_settings", type_="check")
    op.drop_column("server_settings", "geocoding_api_key")
    op.drop_column("server_settings", "geocoding_rate_limit")
    op.drop_column("server_settings", "geocoding_use_https")
    op.drop_column("server_settings", "geocoding_host")
    op.drop_column("server_settings", "geocoding_service")
