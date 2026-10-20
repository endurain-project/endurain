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
truncated to fit the 250-character column.
"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "9a4e6c2d1f73"
down_revision: str | None = "d54bdd779392"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("UPDATE gear SET nickname = btrim(nickname) WHERE nickname <> btrim(nickname)")
    op.execute(
        """
        UPDATE gear
        SET nickname = left(gear.nickname, 250 - length(' (' || gear.id || ')')) || ' (' || gear.id || ')'
        FROM (
            SELECT id,
                   ROW_NUMBER() OVER (PARTITION BY user_id, lower(nickname) ORDER BY id) AS row_position
            FROM gear
        ) ranked
        WHERE gear.id = ranked.id AND ranked.row_position > 1
        """
    )
    op.execute("CREATE UNIQUE INDEX uq_gear_user_nickname ON gear (user_id, lower(nickname))")


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS uq_gear_user_nickname")
