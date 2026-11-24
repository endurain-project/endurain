"""Match text case-insensitively through an ICU collation

Search and the gear nickname lookup compared ``lower()`` of both sides, which does not fold a Greek final sigma
(``ς`` against ``Σ``) or treat composed and decomposed text as equal. The ``case_insensitive`` collation (ICU, secondary
strength, nondeterministic) does both, while accents, ``ß`` and ``ss`` stay different.

The revision creates the collation, renames the gear nicknames the new rule makes equal within one user so the new
unique index can be built, and replaces ``uq_gear_user_nickname`` (``(user_id, lower(nickname))``) with
``(user_id, nickname COLLATE case_insensitive)``. Of a set of equal nicknames the earliest acquired (then lowest id)
keeps its name; each other gets the smallest `` (n)`` suffix, ``n`` from 2, that no gear of that user already
matches. The base is cut, never the suffix, to fit the column. A renamed gear gets its ``version`` bumped and
``updated_at`` stamped, so a client refetches it and ``/sync`` reports it.

The collation needs a PostgreSQL built with ICU.

The downgrade restores the ``lower()`` index and drops the collation; the renamed nicknames keep their new names.

Revision ID: 8d2f61b0c7a4
Revises: 50ac9225ce4f
Create Date: 2026-11-21 00:00:00.000000

"""

from collections.abc import Sequence
import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "8d2f61b0c7a4"
down_revision: str | None = "50ac9225ce4f"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_NICKNAME_LENGTH = 250


def _later_equal_gears(connection: sa.Connection) -> list[sa.Row]:
    """Select the gears that a gear of the same user, earlier in ``(acquired_on, id)`` order, equals by nickname."""
    return list(
        connection.execute(
            sa.text(
                "SELECT later.id, later.user_id, later.nickname FROM gear later "
                "WHERE EXISTS (SELECT 1 FROM gear earlier WHERE earlier.user_id = later.user_id "
                "AND earlier.nickname COLLATE case_insensitive = later.nickname COLLATE case_insensitive "
                "AND (earlier.acquired_on, earlier.id) < (later.acquired_on, later.id)) "
                "ORDER BY later.user_id, later.acquired_on, later.id"
            )
        )
    )


def _free_nickname(connection: sa.Connection, user_id: object, gear_id: object, base: str) -> str:
    """Return ``base`` with the smallest `` (n)`` suffix, ``n >= 2``, that no other gear of the user matches."""
    taken = sa.text(
        "SELECT EXISTS (SELECT 1 FROM gear WHERE user_id = :user_id AND id <> :gear_id "
        "AND nickname COLLATE case_insensitive = :candidate COLLATE case_insensitive)"
    )
    number = 2
    while True:
        suffix = f" ({number})"
        candidate = base[: _NICKNAME_LENGTH - len(suffix)].rstrip() + suffix
        if not connection.execute(taken, {"user_id": user_id, "gear_id": gear_id, "candidate": candidate}).scalar():
            return candidate
        number += 1


def upgrade() -> None:
    """Create the collation, rename nicknames it makes equal, and rebuild the unique nickname index on it."""
    connection = op.get_bind()
    op.execute(
        sa.text(
            "CREATE COLLATION IF NOT EXISTS case_insensitive "
            "(provider = icu, locale = 'und-u-ks-level2', deterministic = false)"
        )
    )
    for gear in _later_equal_gears(connection):
        connection.execute(
            sa.text("UPDATE gear SET nickname = :nickname, version = version + 1, updated_at = now() WHERE id = :id"),
            {"nickname": _free_nickname(connection, gear.user_id, gear.id, gear.nickname), "id": gear.id},
        )
    op.drop_index("uq_gear_user_nickname", table_name="gear")
    op.execute(
        sa.text("CREATE UNIQUE INDEX uq_gear_user_nickname ON gear (user_id, (nickname COLLATE case_insensitive))")
    )


def downgrade() -> None:
    """Restore the ``lower()`` unique index and drop the collation; renamed nicknames keep their new names."""
    op.drop_index("uq_gear_user_nickname", table_name="gear")
    op.execute(sa.text("CREATE UNIQUE INDEX uq_gear_user_nickname ON gear (user_id, lower(nickname))"))
    op.execute(sa.text("DROP COLLATION IF EXISTS case_insensitive"))
