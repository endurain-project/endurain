"""The wire speaks string enums while the database keeps its integers.

A client sends and receives the string; a stored row, a provider sync and an archive written before the strings
still hand over the integer, which is read into the same member; a write puts the integer back.
"""

import uuid
from datetime import UTC, datetime
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

import modules.activities.activity.constants as activity_constants
import modules.activities.activity.schema as activity_schema
import modules.activities.activity.serializers as activity_serializers
import modules.activities.activity_media.contracts as media_contracts
import modules.gears.gear.schema as gear_schema
import modules.gears.gear.serializers as gear_serializers
import modules.health.health_poop.schema as poop_schema
import modules.health.health_sleep.schema as sleep_schema
import modules.notifications.constants as notifications_constants
import modules.notifications.serializers as notifications_serializers
from core.stored_enum import StoredStrEnum, to_stored
from modules.activities.activity_streams.constants import ActivityStreamType

_ENUMS = [
    activity_constants.ActivityType,
    activity_constants.ActivityVisibility,
    activity_constants.MediaType,
    ActivityStreamType,
    gear_schema.GearType,
    notifications_constants.NotificationType,
    poop_schema.BristolType,
    sleep_schema.SleepStageType,
]


@pytest.mark.parametrize("enum", _ENUMS, ids=lambda enum: enum.__name__)
class TestEveryEnum:
    def test_keys_and_stored_integers_are_unique_snake_case(self, enum: type[StoredStrEnum]):
        assert len({member.value for member in enum}) == len(enum)
        assert len({member.stored for member in enum}) == len(enum)
        assert all(member.value == member.value.lower() and " " not in member.value for member in enum)

    def test_the_stored_integer_maps_back_to_the_member(self, enum: type[StoredStrEnum]):
        assert all(enum.from_stored(member.stored) is member for member in enum)


_ROW = {"distance": 0, "name": "Run", "activity_type": 1, "visibility": 2}


class TestActivity:
    def test_a_stored_row_reads_as_keys_and_writes_the_integers_back(self):
        activity = activity_schema.ActivityBase.model_validate(_ROW)

        assert activity.activity_type == "run"
        assert activity.visibility == "private"
        orm = activity_serializers.to_orm(activity)
        assert (orm.activity_type, orm.visibility) == (1, 2)

    def test_an_edit_writes_the_integers(self):
        edit = activity_schema.ActivityEdit(activity_type="trail_run", visibility="followers")

        assert activity_serializers.to_update_values(edit) == {"activity_type": 2, "visibility": 1}

    def test_an_archive_written_with_integers_still_validates(self):
        assert activity_schema.ActivityBase.model_validate({**_ROW, "visibility": 0}).visibility == "public"

    def test_the_json_carries_the_keys(self):
        dumped = activity_schema.ActivityBase.model_validate(_ROW).model_dump(mode="json")

        assert (dumped["activity_type"], dumped["visibility"]) == ("run", "private")


class TestGear:
    def test_a_stored_row_reads_as_the_key(self):
        row = {
            "id": uuid.UUID(int=1),
            "user_id": 1,
            "nickname": "Bike",
            "gear_type": 8,
            "updated_at": datetime(2026, 1, 1, tzinfo=UTC),
        }

        assert gear_schema.GearRead(**row).gear_type == "water_sports_board"

    def test_a_request_refuses_the_integer(self):
        with pytest.raises(ValidationError):
            gear_schema.GearCreateRequest(nickname="Bike", gear_type=1)

    def test_a_create_writes_the_integer(self):
        orm = gear_serializers.to_orm(gear_schema.GearCreateRequest(nickname="Bike", gear_type="shoes"), user_id=1)

        assert orm.gear_type == 2


class TestMedia:
    def test_a_stored_row_reads_as_the_key_and_a_record_writes_the_integer(self):
        record = media_contracts.ActivityMediaCreate(media_path="a.jpg", media_type=1)

        assert record.media_type == "photo"
        assert record.media_type.stored == 1


class TestNotification:
    @staticmethod
    def _row(stored_type):
        return SimpleNamespace(
            id=uuid.UUID(int=1),
            type=stored_type,
            user_id=1,
            read=False,
            created_at=datetime(2026, 1, 1, tzinfo=UTC),
            options={"browser": "Firefox", "operating_system": "Linux", "ip_address": "10.0.0.1"},
        )

    def test_a_stored_row_reads_as_the_key(self):
        read = notifications_serializers.to_read_schema(self._row(33))

        assert read.model_dump(mode="json")["type"] == "new_device_sign_in"

    def test_an_unknown_stored_number_is_refused(self):
        with pytest.raises(ValueError):
            notifications_serializers.to_read_schema(self._row(9999))


class TestHealth:
    _WHEN = datetime(2026, 1, 1, tzinfo=UTC)

    def test_a_bowel_movement_is_written_as_the_scale_number(self):
        create = poop_schema.HealthPoopCreate(date_time=self._WHEN, bristol_type="type_4")

        assert to_stored(create.model_dump())["bristol_type"] == 4
        assert create.model_dump(mode="json")["bristol_type"] == "type_4"

    def test_a_client_bowel_movement_refuses_the_number(self):
        with pytest.raises(ValidationError):
            poop_schema.HealthPoopCreate(date_time=self._WHEN, bristol_type=4)

    def test_an_archived_bowel_movement_with_the_number_is_imported(self):
        record = poop_schema.HealthPoopImport(date_time=self._WHEN, bristol_type=4)

        assert record.bristol_type == "type_4"

    def test_a_sleep_stage_is_stored_as_the_activity_level(self):
        sleep = sleep_schema.HealthSleepCreate(sleep_stages=[{"stage_type": "rem"}])

        assert to_stored(sleep.model_dump())["sleep_stages"][0]["stage_type"] == 2

    def test_a_stored_sleep_stage_reads_as_the_key(self):
        stage = sleep_schema.HealthSleepStage.model_validate(
            SimpleNamespace(stage_type=3, start_time_gmt=None, end_time_gmt=None, duration_seconds=None)
        )

        assert stage.model_dump(mode="json")["stage_type"] == "awake"

    def test_a_client_sleep_stage_refuses_the_number(self):
        with pytest.raises(ValidationError):
            sleep_schema.HealthSleepCreate(sleep_stages=[{"stage_type": 2}])

    def test_an_archived_sleep_record_with_the_number_is_imported(self):
        record = sleep_schema.HealthSleepImport(sleep_stages=[{"stage_type": 2}])

        assert record.sleep_stages is not None
        assert record.sleep_stages[0].stage_type == "rem"
