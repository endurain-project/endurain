"""27: normalise the OpenStreetMap tile URL

Rewrites ``server_settings.tileserver_url`` from the legacy
``https://{s}.tile.openstreetmap.org/...`` default (and the ``a.`` host the
thumbnail fallback used) to ``https://tile.openstreetmap.org/...``, as OSM's
tile usage policy asks. Custom tile servers are left unchanged.

Revision ID: d54bdd779392
Revises: 6f2d8b4e1a97
Create Date: 2026-10-19 00:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "d54bdd779392"
down_revision: str | None = "6f2d8b4e1a97"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_NEW_URL = "https://tile.openstreetmap.org/{z}/{x}/{y}.png"
_LEGACY_URLS: tuple[str, ...] = (
    "https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png",
    "https://a.tile.openstreetmap.org/{z}/{x}/{y}.png",
)


def upgrade() -> None:
    """Point installs still on a legacy OSM URL at the single host."""
    for legacy in _LEGACY_URLS:
        op.execute(
            sa.text("UPDATE server_settings SET tileserver_url = :new WHERE tileserver_url = :old").bindparams(
                new=_NEW_URL, old=legacy
            )
        )


def downgrade() -> None:
    """Leave tileserver_url unchanged.

    The single-host URL works on older versions too, and reverting it would
    also rewrite installs that had set it themselves before this migration.
    """
