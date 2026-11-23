"""The case-insensitive collation revision renames nicknames it makes equal and rebuilds the unique index on it."""

import uuid

import sqlalchemy as sa

from tests._helpers import alembic_chain

_PREVIOUS_HEAD = "50ac9225ce4f"
_LIMIT = 250


def _insert_user(engine) -> uuid.UUID:
    user_id = uuid.uuid4()
    with engine.begin() as connection:
        connection.execute(
            sa.text(
                "INSERT INTO users (id, name, username, email, preferred_language, email_verified, "
                "pending_admin_approval, active, gender, access_type, first_day_of_week, units, currency) "
                "VALUES (:id, 'Ada', :username, :email, 'us', true, false, true, 'female', 'regular', "
                "'monday', 'metric', 'euro')"
            ),
            {"id": user_id, "username": f"u{user_id.hex[:12]}", "email": f"{user_id.hex[:12]}@example.com"},
        )
    return user_id


def _insert_gear(engine, user_id: uuid.UUID, nickname: str, acquired_on: str) -> uuid.UUID:
    gear_id = uuid.uuid4()
    with engine.begin() as connection:
        connection.execute(
            sa.text(
                "INSERT INTO gear (id, user_id, nickname, gear_type, acquired_on, initial_distance, active) "
                "VALUES (:id, :user_id, :nickname, 1, :acquired_on, 0, true)"
            ),
            {"id": gear_id, "user_id": user_id, "nickname": nickname, "acquired_on": acquired_on},
        )
    return gear_id


def _gears(engine, user_id: uuid.UUID) -> dict[uuid.UUID, tuple[str, int]]:
    with engine.connect() as connection:
        rows = connection.execute(sa.text("SELECT id, nickname, version FROM gear WHERE user_id = :u"), {"u": user_id})
        return {row.id: (row.nickname, row.version) for row in rows}


def test_the_upgrade_renames_nicknames_that_only_the_collation_makes_equal(upgrade_db):
    alembic_chain.upgrade(upgrade_db, _PREVIOUS_HEAD)
    owner, other = _insert_user(upgrade_db), _insert_user(upgrade_db)
    oldest = _insert_gear(upgrade_db, owner, "ΟΔΟΣ", "2026-01-01")
    final_sigma = _insert_gear(upgrade_db, owner, "οδος", "2026-01-02")
    decomposed = _insert_gear(upgrade_db, owner, "Café", "2026-01-03")
    composed = _insert_gear(upgrade_db, owner, "Café", "2026-01-04")
    full_width = _insert_gear(upgrade_db, owner, "\uff21\uff22\uff23", "2026-01-05")
    ascii_twin = _insert_gear(upgrade_db, owner, "abc", "2026-01-06")
    taken_suffix = _insert_gear(upgrade_db, owner, "ΟΔΟΣ (2)", "2026-01-07")
    accent = _insert_gear(upgrade_db, owner, "Cafe", "2026-01-10")
    long_base = "Σ" * _LIMIT
    long_oldest = _insert_gear(upgrade_db, owner, long_base, "2026-01-11")
    long_twin_name = "ς" * _LIMIT
    long_twin = _insert_gear(upgrade_db, owner, long_twin_name, "2026-01-12")
    others_gear = _insert_gear(upgrade_db, other, "ΟΔΟΣ", "2026-01-01")
    before = {gear_id: version for gear_id, (_, version) in _gears(upgrade_db, owner).items()}

    alembic_chain.upgrade(upgrade_db, "head")

    after = _gears(upgrade_db, owner)
    assert after[oldest] == ("ΟΔΟΣ", before[oldest])
    assert after[final_sigma] == ("οδος (3)", before[final_sigma] + 1)
    assert after[decomposed] == ("Café", before[decomposed])
    assert after[composed] == ("Café (2)", before[composed] + 1)
    assert after[full_width] == ("\uff21\uff22\uff23", before[full_width])
    assert after[ascii_twin] == ("abc (2)", before[ascii_twin] + 1)
    assert after[taken_suffix] == ("ΟΔΟΣ (2)", before[taken_suffix])
    assert after[accent] == ("Cafe", before[accent])
    assert after[long_oldest] == (long_base, before[long_oldest])
    suffixed, version = after[long_twin]
    assert suffixed == long_twin_name[: _LIMIT - 4] + " (2)"
    assert (len(suffixed), version) == (_LIMIT, before[long_twin] + 1)
    assert _gears(upgrade_db, other) == {others_gear: ("ΟΔΟΣ", 1)}


def test_a_renamed_gear_is_stamped_so_sync_reports_it(upgrade_db):
    alembic_chain.upgrade(upgrade_db, _PREVIOUS_HEAD)
    owner = _insert_user(upgrade_db)
    first = _insert_gear(upgrade_db, owner, "ΟΔΟΣ", "2026-01-01")
    twin = _insert_gear(upgrade_db, owner, "οδος", "2026-01-02")
    kept = _insert_gear(upgrade_db, owner, "Trail", "2026-01-03")
    with upgrade_db.begin() as connection:
        stamp = connection.execute(sa.text("SELECT now() - interval '1 day'")).scalar_one()
        connection.execute(sa.text("UPDATE gear SET updated_at = :stamp"), {"stamp": stamp})

    alembic_chain.upgrade(upgrade_db, "head")

    with upgrade_db.connect() as connection:
        rows = connection.execute(sa.text("SELECT id, updated_at > :stamp AS moved FROM gear"), {"stamp": stamp})
        assert {row.id: row.moved for row in rows} == {first: False, twin: True, kept: False}


def test_the_unique_index_uses_the_collation_and_refuses_an_equal_nickname(upgrade_db):
    alembic_chain.upgrade(upgrade_db, "head")
    owner, other = _insert_user(upgrade_db), _insert_user(upgrade_db)
    _insert_gear(upgrade_db, owner, "ΟΔΟΣ", "2026-01-01")

    with upgrade_db.connect() as connection:
        definition = connection.execute(
            sa.text("SELECT indexdef FROM pg_indexes WHERE indexname = 'uq_gear_user_nickname'")
        ).scalar_one()
    assert "COLLATE case_insensitive" in definition
    assert "UNIQUE" in definition
    assert _insert_gear(upgrade_db, other, "ΟΔΟΣ", "2026-01-01")
    try:
        _insert_gear(upgrade_db, owner, "οδος", "2026-01-02")
    except sa.exc.IntegrityError as error:
        assert "uq_gear_user_nickname" in str(error.orig)
    else:
        raise AssertionError("the unique index accepted a nickname equal under the collation")


def test_the_downgrade_restores_the_lower_index_and_drops_the_collation(upgrade_db):
    alembic_chain.upgrade(upgrade_db, "head")

    alembic_chain.downgrade(upgrade_db, _PREVIOUS_HEAD)

    with upgrade_db.connect() as connection:
        definition = connection.execute(
            sa.text("SELECT indexdef FROM pg_indexes WHERE indexname = 'uq_gear_user_nickname'")
        ).scalar_one()
        collations = connection.execute(
            sa.text("SELECT count(*) FROM pg_collation WHERE collname = 'case_insensitive'")
        )
        assert "lower(" in definition
        assert collations.scalar_one() == 0
