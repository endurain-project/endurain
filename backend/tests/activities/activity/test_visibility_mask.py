"""What a reader who is not the owner never receives of an activity, field by field, as the database returns it."""

from datetime import UTC, datetime

import pytest

import modules.activities.activity.constants as activity_constants
import modules.activities.activity.crud as activity_crud
from tests._factories.activities import make_activity
from tests._factories.gears import make_gear
from tests._factories.users import make_user

_WHOLE = {
    "city": "Porto",
    "town": "Gaia",
    "country": "Portugal",
    "timezone": "Europe/Lisbon",
    "average_hr": 150,
    "max_hr": 180,
    "average_power": 200,
    "max_power": 400,
    "normalized_power": 210,
    "average_cad": 80,
    "max_cad": 100,
    "average_speed": 3.0,
    "max_speed": 6.0,
    "pace": 300.0,
    "elevation_gain": 100,
    "elevation_loss": 90,
}

#: Each hide flag and the fields of the activity it withholds from a reader.
_COVERED = [
    ("hide_location", ("city", "town", "country", "timezone")),
    ("hide_hr", ("average_hr", "max_hr")),
    ("hide_power", ("average_power", "max_power", "normalized_power")),
    ("hide_cadence", ("average_cad", "max_cad")),
    ("hide_speed", ("average_speed", "max_speed")),
    ("hide_pace", ("pace",)),
    ("hide_elevation", ("elevation_gain", "elevation_loss")),
    ("hide_start_time", ("start_time", "end_time", "created_at", "updated_at")),
]


@pytest.fixture
def owner(db):
    return make_user(db, timezone="UTC")


@pytest.fixture
def reader(db):
    return make_user(db, timezone="UTC")


def _read(db, activity, reader_id):
    read = activity_crud.get_activity_by_id_from_user_id_or_has_visibility(activity.id, reader_id, db)
    assert read is not None
    return read


@pytest.mark.parametrize(("flag", "fields"), _COVERED)
class TestAHideFlag:
    def test_a_reader_gets_the_fields_it_covers_cleared_and_the_rest_whole(self, db, owner, reader, flag, fields):
        activity = make_activity(
            db, owner.id, visibility=activity_constants.ActivityVisibility.PUBLIC, **_WHOLE, **{flag: True}
        )

        read = _read(db, activity, reader.id)

        assert all(getattr(read, field) is None for field in fields)
        untouched = [field for field in _WHOLE if field not in fields]
        assert all(getattr(read, field) == _WHOLE[field] for field in untouched)

    def test_the_owner_gets_every_field(self, db, owner, flag, fields):
        activity = make_activity(db, owner.id, **_WHOLE, **{flag: True})

        read = _read(db, activity, owner.id)

        assert all(getattr(read, field) is not None for field in fields)

    def test_a_reader_gets_everything_while_the_flag_is_off(self, db, owner, reader, flag, fields):
        activity = make_activity(db, owner.id, visibility=activity_constants.ActivityVisibility.PUBLIC, **_WHOLE)

        read = _read(db, activity, reader.id)

        assert all(getattr(read, field) is not None for field in fields)


class TestWhatIsNeverSharedWithAReader:
    def test_private_notes_and_provider_identifiers_stay_with_the_owner(self, db, owner, reader):
        activity = make_activity(
            db,
            owner.id,
            visibility=activity_constants.ActivityVisibility.PUBLIC,
            private_notes="mine",
            strava_gear_id="s1",
            garminconnect_gear_id="g1",
            garminconnect_activity_id=5,
            import_info={"file": "x.fit"},
        )

        read = _read(db, activity, reader.id)
        own = _read(db, activity, owner.id)

        assert (read.private_notes, read.strava_gear_id, read.garminconnect_gear_id) == (None, None, None)
        assert (read.garminconnect_activity_id, read.import_info) == (None, None)
        assert (own.private_notes, own.garminconnect_activity_id, own.import_info) == ("mine", 5, {"file": "x.fit"})

    def test_a_hidden_gear_and_a_hidden_map_are_cleared_for_a_reader(self, db, owner, reader):
        gear = make_gear(db, owner.id)
        activity = make_activity(
            db,
            owner.id,
            visibility=activity_constants.ActivityVisibility.PUBLIC,
            gear_id=gear.id,
            hide_gear=True,
            hide_map=True,
        )
        activity_crud.set_activity_thumbnail_key(activity.id, "k.webp", db)

        read = _read(db, activity, reader.id)
        own = _read(db, activity, owner.id)

        assert (read.gear_id, read.map_thumbnail_path) == (None, None)
        assert (own.gear_id, own.map_thumbnail_path) == (gear.id, "k.webp")

    def test_times_come_back_as_aware_utc_instants(self, db, owner):
        activity = make_activity(db, owner.id, start_time=datetime(2026, 7, 15, 9), end_time=datetime(2026, 7, 15, 10))

        read = _read(db, activity, owner.id)

        assert read.start_time == datetime(2026, 7, 15, 9, tzinfo=UTC)
        assert read.start_time.tzinfo is not None
