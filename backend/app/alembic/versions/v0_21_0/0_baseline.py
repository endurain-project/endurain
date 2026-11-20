"""The v0.21 schema, squashed into one baseline

Every revision up to the v0.21 head ran only on an install that upgraded through v0.21.x. Endurain v0.22 upgrades only
from a v0.21.x install, so this revision replaces that whole history: it creates the application schema as the v0.21
head leaves it, and inserts the rows a fresh install holds there (``server_settings``, ``mail_settings`` and the
``v0.19.0`` data migration marker). The statements are in ``0_baseline.sql``, beside this file.

A database already at this revision continues unchanged: it carries the same revision id the v0.21 head had. An older
database is refused by the startup pre-flight (``migrations.startup``) before any revision runs, because the script
directory no longer knows its revision.

Left out on purpose: the UUID conversion scratch table (``uuid_migration_ids``) and the v0.21 data migration rows
(11-14), which the v0.22 revisions remove on a database that has them, and the substrate tables, which JASIL creates
itself (``jasil.migrations``).

Revision ID: e95a7c1d4b36
Revises:
Create Date: 2026-11-19 00:00:00.000000

"""

from collections.abc import Sequence
from pathlib import Path

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "e95a7c1d4b36"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_BASELINE_SQL = Path(__file__).with_name("0_baseline.sql")


def upgrade() -> None:
    """Create the v0.21 application schema and its seed rows."""
    # The script holds no bind-parameter markers, so the driver runs it verbatim.
    op.get_bind().exec_driver_sql(_BASELINE_SQL.read_text(encoding="utf-8"))


def downgrade() -> None:
    """Refuse to downgrade.

    Raises:
        NotImplementedError: Always; the baseline is the start of the history.
    """
    raise NotImplementedError("The baseline is the first revision: restore the database from a backup instead.")
