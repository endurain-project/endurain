"""A multisport activity and its legs through the profile export and import."""

import uuid
from datetime import UTC, datetime

import jasil.providers as platform_providers
import pytest
from sqlalchemy.orm import Session

import modules.activities.activity.integration_service as activity_integration
from tests._factories.activities import make_activity, make_multisport
from tests._factories.ingestion import retain_file
from tests._factories.users import make_user
from tests.activities.activity_profile_transfer import support

_START = datetime(2026, 7, 28, 9, tzinfo=UTC)
_FLAGS = {
    flag: False
    for flag in (
        "hide_start_time",
        "hide_location",
        "hide_map",
        "hide_hr",
        "hide_power",
        "hide_cadence",
        "hide_elevation",
        "hide_speed",
        "hide_pace",
        "hide_laps",
        "hide_workout_sets_steps",
        "hide_gear",
    )
}
_PARENT = "00000000-0000-4000-8000-00000000b001"
_LEG_A = "00000000-0000-4000-8000-00000000b002"
_LEG_B = "00000000-0000-4000-8000-00000000b003"
_ELSEWHERE = "00000000-0000-4000-8000-00000000b00f"


@pytest.fixture
def storage(_publish_local_platform) -> platform_providers.StorageProvider:
    return _publish_local_platform.storage


def _row(activity_id: str, minute: int, activity_type: int, parent: str | None, **overrides):
    row = {
        "id": activity_id,
        "parent_activity_id": parent,
        "distance": 1000,
        "name": f"Row {minute}",
        "activity_type": activity_type,
        "start_time": f"2024-01-01T08:{minute:02d}:00",
        "end_time": f"2024-01-01T09:{minute:02d}:00",
        "total_elapsed_time": 3600.0,
        "total_timer_time": 3600.0,
        "is_hidden": False,
        **_FLAGS,
    }
    row.update(overrides)
    return row


class TestExport:
    def test_the_archive_holds_the_parent_and_each_leg_naming_its_parent(self, db: Session, storage) -> None:
        owner = make_user(db)
        parent, legs = make_multisport(db, owner.id, start=_START)
        alone = make_activity(db, owner.id, name="Alone")

        exported = support.export_activities(db, owner.id, storage, batch_size=2)

        rows = {row["id"]: row for row in exported.json("data/activities.json")}
        assert set(rows) == {str(a.id) for a in (parent, *legs, alone)}
        assert rows[str(parent.id)]["parent_activity_id"] is None
        assert rows[str(alone.id)]["parent_activity_id"] is None
        assert {rows[str(leg.id)]["parent_activity_id"] for leg in legs} == {str(parent.id)}
        assert exported.counts["activities"] == len(legs) + 2

    def test_the_one_retained_file_of_a_group_is_exported_once_under_the_parent(self, db: Session, storage) -> None:
        owner = make_user(db)
        parent, _legs = make_multisport(db, owner.id, start=_START)
        retain_file(owner.id, parent.id, b"fit-bytes", storage)

        exported = support.export_activities(db, owner.id, storage, batch_size=2)

        assert [name for name in exported.names if name.startswith("activity_files/")] == [
            f"activity_files/{parent.id}.fit"
        ]
        assert exported.counts["activity_files"] == 1


class TestImport:
    def test_each_leg_is_restored_under_the_new_id_of_its_parent(self, db: Session, storage) -> None:
        user = make_user(db)
        rows = [
            _row(_PARENT, 0, 48, None),
            _row(_LEG_A, 0, 9, _PARENT),
            _row(_LEG_B, 30, 4, _PARENT),
        ]

        restored = support.import_activities(db, user.id, storage, {"data/activities.json": rows})

        everyone = activity_integration.list_user_activities_page(user.id, db, page_number=1, num_records=100)
        by_type = {activity.activity_type.stored: activity for activity in everyone}
        assert by_type[48].parent_activity_id is None
        assert by_type[9].parent_activity_id == by_type[48].id
        assert by_type[4].parent_activity_id == by_type[48].id
        assert by_type[48].id != uuid.UUID(_PARENT)
        assert restored.counts["activities"] == 3

    def test_a_leg_listed_before_its_parent_is_still_restored_under_it(self, db: Session, storage) -> None:
        user = make_user(db)
        rows = [_row(_LEG_A, 0, 9, _PARENT), _row(_LEG_B, 30, 4, _PARENT), _row(_PARENT, 0, 48, None)]

        support.import_activities(db, user.id, storage, {"data/activities.json": rows}, batch_size=1)

        everyone = activity_integration.list_user_activities_page(user.id, db, page_number=1, num_records=100)
        by_type = {activity.activity_type.stored: activity for activity in everyone}
        assert by_type[9].parent_activity_id == by_type[48].id == by_type[4].parent_activity_id

    def test_a_leg_whose_parent_is_not_in_the_archive_is_restored_as_a_top_level_activity(
        self, db: Session, storage
    ) -> None:
        user = make_user(db)
        rows = [_row(_LEG_A, 0, 9, _ELSEWHERE)]

        support.import_activities(db, user.id, storage, {"data/activities.json": rows})

        [activity] = activity_integration.list_user_activities_page(user.id, db, page_number=1, num_records=100)
        assert activity.parent_activity_id is None

    def test_the_first_leg_that_starts_with_its_parent_is_not_hidden_as_a_duplicate(self, db: Session, storage) -> None:
        user = make_user(db)
        rows = [_row(_PARENT, 0, 48, None), _row(_LEG_A, 0, 9, _PARENT)]

        support.import_activities(db, user.id, storage, {"data/activities.json": rows})

        everyone = activity_integration.list_user_activities_page(user.id, db, page_number=1, num_records=100)
        assert [activity.is_hidden for activity in everyone] == [False, False]

    def test_an_export_restores_into_another_account_as_the_same_group(self, db: Session, storage) -> None:
        source = make_user(db)
        make_multisport(db, source.id, start=_START)
        entries = support.export_activities(db, source.id, storage, batch_size=2).entries
        target = make_user(db)

        support.import_activities(db, target.id, storage, entries)

        everyone = activity_integration.list_user_activities_page(target.id, db, page_number=1, num_records=100)
        [parent] = [activity for activity in everyone if activity.activity_type.stored == 48]
        legs = [activity for activity in everyone if activity.parent_activity_id is not None]
        assert len(legs) == 5
        assert {leg.parent_activity_id for leg in legs} == {parent.id}
        assert all(activity.is_hidden is False for activity in everyone)
