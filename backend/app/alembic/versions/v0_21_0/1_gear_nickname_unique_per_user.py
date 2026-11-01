"""1: enforce gear nickname uniqueness per user

Revision ID: 9a4e6c2d1f73
Revises: d54bdd779392
Create Date: 2026-10-20 00:00:00.000000

Gear creation checks for an existing nickname before inserting, which is
read-then-write: two requests, or a provider sync running beside a manual create,
can both see "not found" and both insert. Once a user has two gears with the same
nickname, every exact-nickname lookup for them fails. The guarantee moves into the
database as a unique index on ``(user_id, lower(nickname))``, matching the
case-insensitive lookup.

Nicknames are trimmed first, as every write path now does. Gears are referenced by
activities and default-gear settings, so duplicates are renamed rather than
deleted: every row after the lowest id of a group gets `` (<id>)`` appended,
truncated to fit the 250-character column. A renamed row can itself collide with a
nickname the user already chose (``Bike (5)``), so the rename repeats until no group
is left with more than one row.

The plain ``nickname`` index is dropped: the new index leads with ``user_id`` and covers
every per-user nickname lookup.

``CREATE UNIQUE INDEX`` is not concurrent, so it blocks writes to ``gear`` while it
builds. The table holds one row per piece of gear a person owns, so that is brief.
"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "9a4e6c2d1f73"
down_revision: str | None = "d54bdd779392"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


_RENAME_DUPLICATES = """
    UPDATE gear
    SET nickname = left(gear.nickname, 250 - length(' (' || gear.id || ')')) || ' (' || gear.id || ')'
    FROM (
        SELECT id,
               ROW_NUMBER() OVER (PARTITION BY user_id, lower(nickname) ORDER BY id) AS row_position
        FROM gear
    ) ranked
    WHERE gear.id = ranked.id AND ranked.row_position > 1
"""

_HAS_DUPLICATES = "SELECT 1 FROM gear GROUP BY user_id, lower(nickname) HAVING count(*) > 1 LIMIT 1"

# Each pass appends a distinct id, so a handful of passes always settles.
_MAX_RENAME_PASSES = 5


def upgrade() -> None:
    connection = op.get_bind()
    op.execute("UPDATE gear SET nickname = btrim(nickname) WHERE nickname <> btrim(nickname)")
    for _ in range(_MAX_RENAME_PASSES):
        op.execute(_RENAME_DUPLICATES)
        if connection.exec_driver_sql(_HAS_DUPLICATES).first() is None:
            break
    op.execute("DROP INDEX IF EXISTS ix_gear_nickname")
    op.execute("CREATE UNIQUE INDEX uq_gear_user_nickname ON gear (user_id, lower(nickname))")


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS uq_gear_user_nickname")
    op.execute("CREATE INDEX IF NOT EXISTS ix_gear_nickname ON gear (nickname)")
