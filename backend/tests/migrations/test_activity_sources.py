"""The activity sources revision converts keys and provider ids into source rows, and its downgrade undoes it."""

import uuid
from datetime import UTC, datetime

import pytest
import sqlalchemy as sa

from tests._helpers import alembic_chain

_PREVIOUS_HEAD = "7d4a9c1e6b52"
_REVISION = "9e3b7a2c5d18"
_MULTISPORT = 48
_SHA = "a" * 64
_OTHER_SHA = "b" * 64
_EPOCH = 1_700_000_000
_START = datetime.fromtimestamp(_EPOCH, tz=UTC)


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


def _insert_activity(
    engine,
    user_id: uuid.UUID,
    *,
    dedup_key: str | None = None,
    strava_id: int | None = None,
    garmin_id: int | None = None,
    parent_id: uuid.UUID | None = None,
    activity_type: int = 1,
    age_days: int = 0,
) -> uuid.UUID:
    activity_id = uuid.uuid4()
    with engine.begin() as connection:
        connection.execute(
            sa.text(
                "INSERT INTO activities (id, user_id, parent_activity_id, dedup_key, strava_activity_id, "
                "garminconnect_activity_id, distance, activity_type, start_time, end_time, created_at, visibility, "
                "total_elapsed_time, total_timer_time, hide_start_time, hide_location, hide_map, hide_hr, hide_power, "
                "hide_cadence, hide_elevation, hide_speed, hide_pace, hide_laps, hide_workout_sets_steps, hide_gear, "
                "is_hidden) VALUES (:id, :user_id, :parent_id, :dedup_key, :strava_id, :garmin_id, 0, :type, "
                "to_timestamp(:epoch), to_timestamp(:epoch), now() - make_interval(days => :age_days), 0, 0, 0, "
                "false, false, false, false, false, false, false, false, false, false, false, false, false)"
            ),
            {
                "id": activity_id,
                "user_id": user_id,
                "parent_id": parent_id,
                "dedup_key": dedup_key,
                "strava_id": strava_id,
                "garmin_id": garmin_id,
                "type": activity_type,
                "epoch": _EPOCH,
                "age_days": age_days,
            },
        )
    return activity_id


def _sources(engine) -> dict[uuid.UUID, list[tuple]]:
    """Return every source as ``(kind, provider id, file hash, start, precedence)``, by activity."""
    with engine.connect() as connection:
        rows = connection.execute(
            sa.text(
                "SELECT activity_id, kind, provider_id, file_sha256, session_start, precedence FROM activity_sources"
            )
        ).all()
    found: dict[uuid.UUID, list[tuple]] = {}
    for row in rows:
        found.setdefault(row.activity_id, []).append(
            (row.kind, row.provider_id, row.file_sha256, row.session_start, row.precedence)
        )
    return found


def _dedup_key(engine, activity_id: uuid.UUID) -> str | None:
    with engine.connect() as connection:
        return connection.execute(
            sa.text("SELECT dedup_key FROM activities WHERE id = :id"), {"id": activity_id}
        ).scalar_one()


def test_the_upgrade_creates_the_table_with_its_constraints_and_indexes(upgrade_db):
    alembic_chain.upgrade(upgrade_db, _REVISION)

    inspector = sa.inspect(upgrade_db)
    columns = {column["name"]: column for column in inspector.get_columns("activity_sources")}
    assert set(columns) == {
        "id",
        "activity_id",
        "user_id",
        "kind",
        "provider_id",
        "file_sha256",
        "session_start",
        "precedence",
        "received_at",
    }
    assert all(column["comment"] for name, column in columns.items() if name != "id")
    indexes = {index["name"]: index for index in inspector.get_indexes("activity_sources")}
    assert indexes["uq_activity_sources_provider"]["unique"] is True
    assert indexes["uq_activity_sources_provider"]["column_names"] == [
        "user_id",
        "kind",
        "provider_id",
        "session_start",
    ]
    assert indexes["uq_activity_sources_file"]["column_names"] == ["user_id", "file_sha256", "session_start"]
    assert indexes["ix_activity_sources_activity_id_kind"]["column_names"] == ["activity_id", "kind"]
    assert {constraint["name"] for constraint in inspector.get_check_constraints("activity_sources")} == {
        "ck_activity_sources_kind",
        "ck_activity_sources_one_identity",
    }
    assert "ix_activities_user_id_start_time" not in {index["name"] for index in inspector.get_indexes("activities")}


class TestTheConversion:
    def test_every_key_shape_becomes_the_source_it_named(self, upgrade_db):
        alembic_chain.upgrade(upgrade_db, _PREVIOUS_HEAD)
        user_id = _insert_user(upgrade_db)
        strava = _insert_activity(upgrade_db, user_id, dedup_key="strava:9000000001")
        garmin_bare = _insert_activity(upgrade_db, user_id, dedup_key="garmin:77")
        garmin_salted = _insert_activity(upgrade_db, user_id, dedup_key=f"garmin:77:{_EPOCH}")
        file_bare = _insert_activity(upgrade_db, user_id, dedup_key=f"file:{_SHA}")
        file_salted = _insert_activity(upgrade_db, user_id, dedup_key=f"file:{_OTHER_SHA}:{_EPOCH}")
        keyless = _insert_activity(upgrade_db, user_id)
        malformed = _insert_activity(upgrade_db, user_id, dedup_key="file:not-a-hash")

        alembic_chain.upgrade(upgrade_db, _REVISION)

        sources = _sources(upgrade_db)
        assert sources[strava] == [("strava", 9000000001, None, None, 0)]
        assert sources[garmin_bare] == [("garmin", 77, None, None, 2)]
        assert sources[garmin_salted] == [("garmin", 77, None, _START, 2)]
        assert sources[file_bare] == [("file", None, _SHA, None, 2)]
        assert sources[file_salted] == [("file", None, _OTHER_SHA, _START, 2)]
        assert keyless not in sources
        assert malformed not in sources
        assert _dedup_key(upgrade_db, strava) == "strava:9000000001", "the legacy key is left as it is"

    def test_a_multisport_parent_and_its_legs_keep_the_identity_their_keys_named(self, upgrade_db):
        alembic_chain.upgrade(upgrade_db, _PREVIOUS_HEAD)
        user_id = _insert_user(upgrade_db)
        parent = _insert_activity(upgrade_db, user_id, dedup_key=f"file:{_SHA}", activity_type=_MULTISPORT)
        leg = _insert_activity(upgrade_db, user_id, dedup_key=f"file:{_SHA}:{_EPOCH}", parent_id=parent)

        alembic_chain.upgrade(upgrade_db, _REVISION)

        sources = _sources(upgrade_db)
        assert sources[parent] == [("file", None, _SHA, None, 2)]
        assert sources[leg] == [("file", None, _SHA, _START, 2)]

    def test_a_row_hidden_as_a_duplicate_is_converted_like_any_other(self, upgrade_db):
        alembic_chain.upgrade(upgrade_db, _PREVIOUS_HEAD)
        user_id = _insert_user(upgrade_db)
        original = _insert_activity(upgrade_db, user_id, dedup_key="garmin:5")
        duplicate = _insert_activity(upgrade_db, user_id, dedup_key=f"file:{_SHA}:{_EPOCH}")
        with upgrade_db.begin() as connection:
            connection.execute(sa.text("UPDATE activities SET is_hidden = true WHERE id = :id"), {"id": duplicate})

        alembic_chain.upgrade(upgrade_db, _REVISION)

        sources = _sources(upgrade_db)
        assert original in sources
        assert sources[duplicate] == [("file", None, _SHA, _START, 2)]

    def test_provider_ids_without_a_key_become_sources_once_per_id(self, upgrade_db):
        """A profile restore sets the id columns and no key; one restored twice leaves two rows with one id."""
        alembic_chain.upgrade(upgrade_db, _PREVIOUS_HEAD)
        user_id = _insert_user(upgrade_db)
        other_user = _insert_user(upgrade_db)
        older = _insert_activity(upgrade_db, user_id, strava_id=42, garmin_id=43, age_days=2)
        newer = _insert_activity(upgrade_db, user_id, strava_id=42, garmin_id=43)
        theirs = _insert_activity(upgrade_db, other_user, strava_id=42)

        alembic_chain.upgrade(upgrade_db, _REVISION)

        sources = _sources(upgrade_db)
        assert sorted(sources[older]) == [("garmin", 43, None, None, 2), ("strava", 42, None, None, 0)]
        assert newer not in sources
        assert sources[theirs] == [("strava", 42, None, None, 0)]

    def test_a_provider_id_whose_key_already_made_a_source_adds_no_second_one(self, upgrade_db):
        alembic_chain.upgrade(upgrade_db, _PREVIOUS_HEAD)
        user_id = _insert_user(upgrade_db)
        keyed = _insert_activity(upgrade_db, user_id, dedup_key="strava:7", strava_id=7)

        alembic_chain.upgrade(upgrade_db, _REVISION)

        assert _sources(upgrade_db)[keyed] == [("strava", 7, None, None, 0)]

    def test_a_restored_leg_takes_the_id_with_its_own_start_and_its_parent_the_bare_id(self, upgrade_db):
        alembic_chain.upgrade(upgrade_db, _PREVIOUS_HEAD)
        user_id = _insert_user(upgrade_db)
        parent = _insert_activity(upgrade_db, user_id, garmin_id=88, activity_type=_MULTISPORT)
        leg = _insert_activity(upgrade_db, user_id, garmin_id=88, parent_id=parent)

        alembic_chain.upgrade(upgrade_db, _REVISION)

        sources = _sources(upgrade_db)
        assert sources[parent] == [("garmin", 88, None, None, 2)]
        assert sources[leg] == [("garmin", 88, None, _START, 2)]


class TestTheConstraints:
    @pytest.fixture
    def activity(self, upgrade_db):
        alembic_chain.upgrade(upgrade_db, _REVISION)
        user_id = _insert_user(upgrade_db)
        return user_id, _insert_activity(upgrade_db, user_id)

    @staticmethod
    def _insert(engine, activity, **values) -> None:
        user_id, activity_id = activity
        row = {"kind": "file", "provider_id": None, "file_sha256": None, "session_start": None, "precedence": 2}
        row.update(values)
        with engine.begin() as connection:
            connection.execute(
                sa.text(
                    "INSERT INTO activity_sources (id, activity_id, user_id, kind, provider_id, file_sha256, "
                    "session_start, precedence) VALUES (gen_random_uuid(), :activity_id, :user_id, :kind, "
                    ":provider_id, :file_sha256, :session_start, :precedence)"
                ),
                {"activity_id": activity_id, "user_id": user_id, **row},
            )

    def test_a_null_start_is_a_value_of_its_own_in_the_uniqueness(self, upgrade_db, activity):
        self._insert(upgrade_db, activity, kind="strava", provider_id=1)

        with pytest.raises(sa.exc.IntegrityError):
            self._insert(upgrade_db, activity, kind="strava", provider_id=1)
        self._insert(upgrade_db, activity, kind="garmin", provider_id=1)
        self._insert(upgrade_db, activity, kind="garmin", provider_id=1, session_start=_START)

    def test_a_file_hash_is_unique_per_start_so_one_multi_activity_file_holds_several(self, upgrade_db, activity):
        self._insert(upgrade_db, activity, file_sha256=_SHA, session_start=_START)
        self._insert(upgrade_db, activity, file_sha256=_SHA, session_start=datetime(2023, 1, 1, tzinfo=UTC))

        with pytest.raises(sa.exc.IntegrityError):
            self._insert(upgrade_db, activity, file_sha256=_SHA, session_start=_START)

    def test_a_source_has_exactly_one_identity_and_a_known_kind(self, upgrade_db, activity):
        with pytest.raises(sa.exc.IntegrityError):
            self._insert(upgrade_db, activity, kind="garmin")
        with pytest.raises(sa.exc.IntegrityError):
            self._insert(upgrade_db, activity, kind="garmin", provider_id=1, file_sha256=_SHA)
        with pytest.raises(sa.exc.IntegrityError):
            self._insert(upgrade_db, activity, kind="other", provider_id=1)

    def test_the_same_identity_of_another_user_is_a_different_source(self, upgrade_db, activity):
        other = (_insert_user(upgrade_db), None)
        other_activity = (other[0], _insert_activity(upgrade_db, other[0]))
        self._insert(upgrade_db, activity, kind="strava", provider_id=1)

        self._insert(upgrade_db, other_activity, kind="strava", provider_id=1)

    def test_deleting_an_activity_deletes_its_sources(self, upgrade_db, activity):
        self._insert(upgrade_db, activity, kind="strava", provider_id=1)

        with upgrade_db.begin() as connection:
            connection.execute(sa.text("DELETE FROM activities WHERE id = :id"), {"id": activity[1]})

        assert _sources(upgrade_db) == {}


class TestTheDowngrade:
    def test_it_rebuilds_a_missing_key_from_the_oldest_source_and_drops_the_table(self, upgrade_db):
        alembic_chain.upgrade(upgrade_db, _REVISION)
        user_id = _insert_user(upgrade_db)
        strava = _insert_activity(upgrade_db, user_id)
        file_salted = _insert_activity(upgrade_db, user_id)
        garmin_bare = _insert_activity(upgrade_db, user_id)
        keyed = _insert_activity(upgrade_db, user_id, dedup_key="strava:1")
        with upgrade_db.begin() as connection:
            for activity_id, kind, provider_id, sha, start in (
                (strava, "strava", 9000000001, None, None),
                (file_salted, "file", None, _SHA, _START),
                (garmin_bare, "garmin", 77, None, None),
                (keyed, "strava", 2, None, None),
            ):
                connection.execute(
                    sa.text(
                        "INSERT INTO activity_sources (id, activity_id, user_id, kind, provider_id, file_sha256, "
                        "session_start, precedence) VALUES (gen_random_uuid(), :a, :u, :k, :p, :s, :t, 0)"
                    ),
                    {"a": activity_id, "u": user_id, "k": kind, "p": provider_id, "s": sha, "t": start},
                )

        alembic_chain.downgrade(upgrade_db, _PREVIOUS_HEAD)

        assert "activity_sources" not in set(sa.inspect(upgrade_db).get_table_names())
        assert _dedup_key(upgrade_db, strava) == "strava:9000000001"
        assert _dedup_key(upgrade_db, file_salted) == f"file:{_SHA}:{_EPOCH}"
        assert _dedup_key(upgrade_db, garmin_bare) == "garmin:77"
        assert _dedup_key(upgrade_db, keyed) == "strava:1", "a key an activity has is left as it is"

    def test_a_conversion_followed_by_a_downgrade_gives_back_the_keys(self, upgrade_db):
        alembic_chain.upgrade(upgrade_db, _PREVIOUS_HEAD)
        user_id = _insert_user(upgrade_db)
        keys = ["strava:5", f"garmin:6:{_EPOCH}", "garmin:7", f"file:{_SHA}", f"file:{_OTHER_SHA}:{_EPOCH}"]
        ids = [_insert_activity(upgrade_db, user_id, dedup_key=key) for key in keys]

        alembic_chain.upgrade(upgrade_db, _REVISION)
        with upgrade_db.begin() as connection:
            connection.execute(sa.text("UPDATE activities SET dedup_key = NULL"))
        alembic_chain.downgrade(upgrade_db, _PREVIOUS_HEAD)

        assert [_dedup_key(upgrade_db, activity_id) for activity_id in ids] == keys
