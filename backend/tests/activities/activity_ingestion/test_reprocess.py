"""Reprocessing one activity in place from its retained file: what it recomputes, what it must never touch."""

import dataclasses
import json
import shutil
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import MagicMock

import jasil.publisher as platform_publisher
import pytest
from sqlalchemy import delete, select, update
from sqlalchemy.orm import Session

import core.exceptions as core_exceptions
import modules.activities.activity.constants as activity_constants
import modules.activities.activity.models as activity_models
import modules.activities.activity_exercise_titles.models as exercise_title_models
import modules.activities.activity_file_storage.constants as file_storage_constants
import modules.activities.activity_file_storage.files as file_storage_files
import modules.activities.activity_file_storage.integration_service as file_storage
import modules.activities.activity_ingestion.contracts as ingestion_contracts
import modules.activities.activity_ingestion.migration_service as migration_service
import modules.activities.activity_ingestion.pipeline_service as pipeline_service
import modules.activities.activity_laps.models as lap_models
import modules.activities.activity_sets.models as set_models
import modules.activities.activity_streams.constants as stream_constants
import modules.activities.activity_streams.models as stream_models
import modules.activities.activity_workout_steps.models as step_models
import modules.activities.computation as activities_computation
import modules.users.users.models as user_models
from tests._factories.ingestion import fit_file
from tests._factories.users import make_user

_FIXTURES = Path(__file__).parents[1] / "activity_file_import" / "fixtures"
_RUN = _FIXTURES / "outdoor_run" / "24273515840_ACTIVITY.fit"
_STRENGTH = _FIXTURES / "strength" / "24939814804_ACTIVITY.fit"
_TRIATHLON = _FIXTURES / "triathlon" / "24846754341_ACTIVITY.fit"
_TREADMILL = _FIXTURES / "treadmill_run" / "24280055123_ACTIVITY.fit"

#: Written independently of ``activity_constants.DERIVED_FIELDS``, so a column the code forgets shows as a failure.
_DERIVED = (
    "distance",
    "end_time",
    "timezone",
    "total_elapsed_time",
    "total_timer_time",
    "elevation_gain",
    "elevation_loss",
    "pace",
    "average_speed",
    "max_speed",
    "average_power",
    "max_power",
    "normalized_power",
    "average_hr",
    "max_hr",
    "average_cad",
    "max_cad",
    "workout_feeling",
    "workout_rpe",
    "calories",
    "tracker_manufacturer",
    "tracker_model",
    "total_cycles",
)

#: What the owner, a provider or geocoding owns: a reprocess leaves every one as it is.
_OWNED = (
    "name",
    "description",
    "private_notes",
    "activity_type",
    "visibility",
    "is_hidden",
    "gear_id",
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
    "city",
    "town",
    "country",
    "strava_activity_id",
    "garminconnect_activity_id",
    "dedup_key",
    "import_info",
    "start_time",
    "created_at",
    "user_id",
    "parent_activity_id",
)

_OLD = datetime(2020, 1, 1, tzinfo=UTC)

_BOGUS_DERIVED = {
    "distance": 1,
    "end_time": _OLD,
    "timezone": "Etc/GMT",
    "total_elapsed_time": 1,
    "total_timer_time": 1,
    "elevation_gain": 999,
    "elevation_loss": 999,
    "pace": 9,
    "average_speed": 9,
    "max_speed": 9,
    "average_power": 999,
    "max_power": 999,
    "normalized_power": 999,
    "average_hr": 99,
    "max_hr": 99,
    "average_cad": 99,
    "max_cad": 99,
    "workout_feeling": 1,
    "workout_rpe": 10,
    "calories": 1,
    "tracker_manufacturer": "old",
    "tracker_model": "old",
    "total_cycles": 1,
}


@pytest.fixture
def owner(db: Session):
    """A user whose timezone and units the reprocess reads."""
    user = make_user(db, timezone="Europe/Lisbon")
    db.commit()
    return user


@pytest.fixture
def other(db: Session):
    """A second user importing the same files, whose fresh import is the oracle."""
    user = make_user(db, timezone="Europe/Lisbon")
    db.commit()
    return user


@pytest.fixture
def published(monkeypatch) -> MagicMock:
    """A spy on the event facade, so a test can say nothing was published."""
    spy = MagicMock()
    monkeypatch.setattr(platform_publisher, "publish_on_commit", spy)
    return spy


def _import(db: Session, user_id: uuid.UUID, source: Path, tmp_path: Path, storage) -> list[uuid.UUID]:
    """Import a fixture file through the real pipeline and return the stored top-level activity ids."""
    staged = tmp_path / f"{uuid.uuid4().hex}{source.suffix}"
    shutil.copyfile(source, staged)
    created = pipeline_service.validate_prepare_and_store_file(
        user_id, str(staged), db, source=ingestion_contracts.UploadSource(), storage=storage
    )
    db.commit()
    assert created
    return [activity.id for activity in created]


def _import_legacy_legs(
    db: Session, user_id: uuid.UUID, source: Path, tmp_path: Path, storage, monkeypatch
) -> list[uuid.UUID]:
    """Import a multi-session file the way it was stored before groups: one activity and one file copy per session."""
    real = pipeline_service.parse_file

    def without_a_parent(*args, **kwargs):
        return dataclasses.replace(real(*args, **kwargs), parent=None)

    with monkeypatch.context() as patch:
        patch.setattr(pipeline_service, "parse_file", without_a_parent)
        return _import(db, user_id, source, tmp_path, storage)


def _row(db: Session, activity_id: uuid.UUID) -> activity_models.Activity:
    db.expire_all()
    return db.execute(select(activity_models.Activity).where(activity_models.Activity.id == activity_id)).scalar_one()


def _values(db: Session, activity_id: uuid.UUID, columns: tuple[str, ...]) -> dict[str, object]:
    row = _row(db, activity_id)
    return {column: getattr(row, column) for column in columns}


def _children(db: Session, activity_id: uuid.UUID) -> dict[str, list[str]]:
    """Every child row of an activity as canonical text, so two activities compare by content."""
    db.expire_all()
    snapshot: dict[str, list[str]] = {}
    for name, model in (
        ("streams", stream_models.ActivityStreams),
        ("laps", lap_models.ActivityLaps),
        ("sets", set_models.ActivitySets),
        ("steps", step_models.ActivityWorkoutSteps),
    ):
        columns = [column.key for column in model.__table__.columns if column.key not in ("id", "activity_id")]
        rows = db.execute(select(model).where(model.activity_id == activity_id)).scalars().all()
        snapshot[name] = sorted(
            json.dumps({column: getattr(row, column) for column in columns}, sort_keys=True, default=str)
            for row in rows
        )
    return snapshot


def _degrade(db: Session, activity_id: uuid.UUID) -> None:
    """Make an activity look like one an older analysis stored: version 0, old values, an extra child of each kind."""
    db.execute(
        update(activity_models.Activity)
        .where(activity_models.Activity.id == activity_id)
        .values(**_BOGUS_DERIVED, analysis_version=0, updated_at=_OLD)
    )
    db.add_all(
        [
            stream_models.ActivityStreams(
                activity_id=activity_id,
                stream_type=stream_constants.STREAM_TYPE_HR,
                stream_waypoints=[{"time": "2000-01-01T00:00:00", "hr": 1}],
            ),
            lap_models.ActivityLaps(activity_id=activity_id, start_time=_OLD, total_distance=1),
            set_models.ActivitySets(
                activity_id=activity_id, duration=1, set_type="old", start_time=_OLD, repetitions=1
            ),
            step_models.ActivityWorkoutSteps(activity_id=activity_id, message_index=99),
        ]
    )
    db.commit()


def _store_timezone(db: Session, activity_id: uuid.UUID, timezone: str | None) -> None:
    """Set the timezone an older analysis stored for an activity."""
    db.execute(
        update(activity_models.Activity).where(activity_models.Activity.id == activity_id).values(timezone=timezone)
    )
    db.commit()


def _logged(caplog, activity_id: uuid.UUID) -> bool:
    """Return whether a record names the activity in its structured fields."""
    return any(str(getattr(record, "activity_id", None)) == str(activity_id) for record in caplog.records)


def _fresh(db: Session, user_id: uuid.UUID, source: Path, tmp_path: Path, storage) -> uuid.UUID:
    """Return the activity a fresh import of the file stores for another user."""
    [activity_id] = _import(db, user_id, source, tmp_path, storage)
    return activity_id


class TestReprocessingOneActivity:
    def test_recomputes_what_a_fresh_import_stores(self, db, owner, other, storage, tmp_path):
        [activity_id] = _import(db, owner.id, _RUN, tmp_path, storage)
        expected = _fresh(db, other.id, _RUN, tmp_path, storage)
        _degrade(db, activity_id)

        outcome = migration_service.reprocess_activity(activity_id, storage)

        assert outcome is migration_service.ReprocessOutcome.REPROCESSED
        assert _values(db, activity_id, _DERIVED) == _values(db, expected, _DERIVED)

    def test_replaces_streams_laps_sets_and_steps_exactly_once(self, db, owner, other, storage, tmp_path):
        [activity_id] = _import(db, owner.id, _STRENGTH, tmp_path, storage)
        expected = _children(db, _fresh(db, other.id, _STRENGTH, tmp_path, storage))
        assert expected["sets"] and expected["steps"]
        _degrade(db, activity_id)

        migration_service.reprocess_activity(activity_id, storage)

        assert _children(db, activity_id) == expected

    def test_replaces_the_children_of_a_run_with_a_track(self, db, owner, other, storage, tmp_path):
        [activity_id] = _import(db, owner.id, _RUN, tmp_path, storage)
        expected = _children(db, _fresh(db, other.id, _RUN, tmp_path, storage))
        assert expected["streams"] and expected["laps"]
        _degrade(db, activity_id)

        migration_service.reprocess_activity(activity_id, storage)

        assert _children(db, activity_id) == expected

    def test_never_writes_what_the_owner_edited(self, db, owner, storage, tmp_path):
        [activity_id] = _import(db, owner.id, _RUN, tmp_path, storage)
        edits = {
            "name": "My long run",
            "description": "felt great",
            "private_notes": "knee",
            "activity_type": activity_constants.ActivityType.RIDE.stored,
            "visibility": activity_constants.ActivityVisibility.PRIVATE.stored,
            "is_hidden": True,
            **{field: True for field in _OWNED if field.startswith("hide_")},
        }
        db.execute(update(activity_models.Activity).where(activity_models.Activity.id == activity_id).values(**edits))
        db.commit()
        _degrade(db, activity_id)
        before = _values(db, activity_id, _OWNED)

        migration_service.reprocess_activity(activity_id, storage)

        assert _values(db, activity_id, _OWNED) == before
        assert all(_values(db, activity_id, tuple(edits)).get(field) == value for field, value in edits.items())

    def test_keeps_the_version_and_stamps_the_analysis_version_and_updated_at(self, db, owner, storage, tmp_path):
        [activity_id] = _import(db, owner.id, _RUN, tmp_path, storage)
        _degrade(db, activity_id)
        before = _row(db, activity_id)
        version = before.version
        assert before.analysis_version == 0

        migration_service.reprocess_activity(activity_id, storage)

        after = _row(db, activity_id)
        assert after.version == version
        assert after.analysis_version == activities_computation.ANALYSIS_VERSION
        assert after.updated_at > _OLD

    def test_is_idempotent(self, db, owner, storage, tmp_path):
        [activity_id] = _import(db, owner.id, _STRENGTH, tmp_path, storage)
        _degrade(db, activity_id)

        migration_service.reprocess_activity(activity_id, storage)
        once = (_values(db, activity_id, _DERIVED), _children(db, activity_id))
        outcome = migration_service.reprocess_activity(activity_id, storage)

        assert outcome is migration_service.ReprocessOutcome.REPROCESSED
        assert (_values(db, activity_id, _DERIVED), _children(db, activity_id)) == once

    def test_publishes_no_event(self, db, owner, storage, tmp_path, published):
        [activity_id] = _import(db, owner.id, _RUN, tmp_path, storage)
        published.reset_mock()
        _degrade(db, activity_id)

        migration_service.reprocess_activity(activity_id, storage)

        published.assert_not_called()

    def test_an_activity_stored_without_a_zone_takes_the_owners_timezone(self, db, storage, tmp_path):
        tokyo = make_user(db, timezone="Asia/Tokyo")
        db.commit()
        without_a_zone = tmp_path / "no_gps.fit"
        without_a_zone.write_bytes(fit_file(with_gps=False))
        [activity_id] = _import(db, tokyo.id, without_a_zone, tmp_path, storage)
        _degrade(db, activity_id)
        _store_timezone(db, activity_id, None)

        migration_service.reprocess_activity(activity_id, storage)

        assert _row(db, activity_id).timezone == "Asia/Tokyo"

    def test_a_file_without_a_zone_keeps_the_zone_it_was_imported_in_after_the_owner_moves(self, db, storage, tmp_path):
        traveller = make_user(db, timezone="Asia/Tokyo")
        db.commit()
        without_a_zone = tmp_path / "no_gps.fit"
        without_a_zone.write_bytes(fit_file(with_gps=False))
        [activity_id] = _import(db, traveller.id, without_a_zone, tmp_path, storage)
        _degrade(db, activity_id)
        # An old row holds the zone it was imported in; the owner moved since.
        _store_timezone(db, activity_id, "Asia/Tokyo")
        db.execute(
            update(user_models.Users).where(user_models.Users.id == traveller.id).values(timezone="Europe/Lisbon")
        )
        db.commit()

        migration_service.reprocess_activity(activity_id, storage)

        assert _row(db, activity_id).timezone == "Asia/Tokyo"

    def test_re_adds_the_exercise_titles_of_the_file(self, db, owner, storage, tmp_path):
        [activity_id] = _import(db, owner.id, _STRENGTH, tmp_path, storage)
        stored = db.execute(select(exercise_title_models.ActivityExerciseTitles)).scalars().all()
        assert stored
        db.execute(delete(exercise_title_models.ActivityExerciseTitles))
        _degrade(db, activity_id)

        migration_service.reprocess_activity(activity_id, storage)

        assert len(db.execute(select(exercise_title_models.ActivityExerciseTitles)).scalars().all()) == len(stored)

    def test_leaves_another_users_activity_alone(self, db, owner, other, storage, tmp_path):
        [activity_id] = _import(db, owner.id, _RUN, tmp_path, storage)
        neighbour = _fresh(db, other.id, _RUN, tmp_path, storage)
        _degrade(db, activity_id)
        _degrade(db, neighbour)
        before = (_values(db, neighbour, _DERIVED), _children(db, neighbour), _row(db, neighbour).analysis_version)

        migration_service.reprocess_activity(activity_id, storage)

        assert (
            _values(db, neighbour, _DERIVED),
            _children(db, neighbour),
            _row(db, neighbour).analysis_version,
        ) == before


class TestTheThumbnail:
    def _map_stream(self, db: Session, activity_id: uuid.UUID) -> stream_models.ActivityStreams:
        db.expire_all()
        return db.execute(
            select(stream_models.ActivityStreams).where(
                stream_models.ActivityStreams.activity_id == activity_id,
                stream_models.ActivityStreams.stream_type == stream_constants.STREAM_TYPE_MAP,
            )
        ).scalar_one()

    def _set_key(self, db: Session, activity_id: uuid.UUID, key: str | None) -> None:
        db.execute(
            update(activity_models.Activity)
            .where(activity_models.Activity.id == activity_id)
            .values(map_thumbnail_path=key)
        )
        db.commit()

    def test_is_kept_when_the_track_is_the_same(self, db, owner, storage, tmp_path):
        [activity_id] = _import(db, owner.id, _RUN, tmp_path, storage)
        self._set_key(db, activity_id, f"{activity_id}.webp")
        db.execute(
            update(activity_models.Activity)
            .where(activity_models.Activity.id == activity_id)
            .values(**_BOGUS_DERIVED, analysis_version=0)
        )
        db.commit()

        migration_service.reprocess_activity(activity_id, storage)

        assert _row(db, activity_id).map_thumbnail_path == f"{activity_id}.webp"

    def test_is_cleared_when_the_track_changed(self, db, owner, storage, tmp_path):
        [activity_id] = _import(db, owner.id, _RUN, tmp_path, storage)
        self._set_key(db, activity_id, f"{activity_id}.webp")
        track = self._map_stream(db, activity_id)
        track.stream_waypoints = [{**point, "lat": point["lat"] + 1} for point in track.stream_waypoints]
        db.commit()

        migration_service.reprocess_activity(activity_id, storage)

        assert _row(db, activity_id).map_thumbnail_path is None

    def test_is_kept_for_an_activity_with_no_track(self, db, owner, storage, tmp_path):
        [activity_id] = _import(db, owner.id, _TREADMILL, tmp_path, storage)
        self._set_key(db, activity_id, f"{activity_id}.webp")

        migration_service.reprocess_activity(activity_id, storage)

        assert _row(db, activity_id).map_thumbnail_path == f"{activity_id}.webp"


class TestWhenNothingCanBeReprocessed:
    def test_an_activity_without_a_retained_file_is_left_as_it_is(self, db, owner, storage, tmp_path):
        [activity_id] = _import(db, owner.id, _RUN, tmp_path, storage)
        _degrade(db, activity_id)
        key, _data = file_storage.get_activity_file(activity_id, storage)
        storage.delete(file_storage_constants.ACTIVITY_FILE_STORAGE_AREA, file_storage_files.processed_storage_key(key))
        before = (_values(db, activity_id, _DERIVED), _children(db, activity_id))

        outcome = migration_service.reprocess_activity(activity_id, storage)

        assert outcome is migration_service.ReprocessOutcome.NO_FILE
        assert (_values(db, activity_id, _DERIVED), _children(db, activity_id)) == before
        assert _row(db, activity_id).analysis_version == 0

    def test_an_unknown_activity_has_no_file(self, db, storage):
        assert migration_service.reprocess_activity(uuid.uuid4(), storage) is migration_service.ReprocessOutcome.NO_FILE

    def test_a_corrupted_file_fails_and_changes_nothing(self, db, owner, storage, tmp_path, caplog):
        [activity_id] = _import(db, owner.id, _RUN, tmp_path, storage)
        _degrade(db, activity_id)
        file_storage.store_activity_file(activity_id, ".fit", b"this is not a fit file at all", storage)
        before = (_values(db, activity_id, _DERIVED), _children(db, activity_id))

        outcome = migration_service.reprocess_activity(activity_id, storage)

        assert outcome is migration_service.ReprocessOutcome.FAILED
        assert (_values(db, activity_id, _DERIVED), _children(db, activity_id)) == before
        assert _row(db, activity_id).analysis_version == 0
        assert _logged(caplog, activity_id)

    def test_a_parse_refusal_fails(self, db, owner, storage, tmp_path, monkeypatch):
        [activity_id] = _import(db, owner.id, _RUN, tmp_path, storage)

        def refuse(*_args, **_kwargs):
            raise core_exceptions.InvalidInputError("no")

        monkeypatch.setattr(pipeline_service, "parse_file", refuse)

        assert migration_service.reprocess_activity(activity_id, storage) is migration_service.ReprocessOutcome.FAILED

    def test_a_file_with_no_session_at_the_start_has_no_session(self, db, owner, storage, tmp_path, caplog):
        [activity_id] = _import(db, owner.id, _RUN, tmp_path, storage)
        _degrade(db, activity_id)
        db.execute(
            update(activity_models.Activity)
            .where(activity_models.Activity.id == activity_id)
            .values(start_time=_row(db, activity_id).start_time + timedelta(hours=1))
        )
        db.commit()
        before = (_values(db, activity_id, _DERIVED), _children(db, activity_id))

        outcome = migration_service.reprocess_activity(activity_id, storage)

        assert outcome is migration_service.ReprocessOutcome.NO_SESSION
        assert (_values(db, activity_id, _DERIVED), _children(db, activity_id)) == before
        assert _row(db, activity_id).analysis_version == 0
        assert _logged(caplog, activity_id)

    def test_a_start_stored_in_whole_seconds_still_matches(self, db, owner, storage, tmp_path):
        [activity_id] = _import(db, owner.id, _RUN, tmp_path, storage)
        _degrade(db, activity_id)
        db.execute(
            update(activity_models.Activity)
            .where(activity_models.Activity.id == activity_id)
            .values(start_time=_row(db, activity_id).start_time - timedelta(milliseconds=900))
        )
        db.commit()

        outcome = migration_service.reprocess_activity(activity_id, storage)

        assert outcome is migration_service.ReprocessOutcome.REPROCESSED


class TestAMultiSessionFile:
    def test_each_legacy_activity_is_reprocessed_from_the_session_it_started(
        self, db, owner, other, storage, tmp_path, monkeypatch
    ):
        legacy = _import_legacy_legs(db, owner.id, _TRIATHLON, tmp_path, storage, monkeypatch)
        [parent_id] = _import(db, other.id, _TRIATHLON, tmp_path, storage)
        db.expire_all()
        legs = (
            db.execute(
                select(activity_models.Activity.id)
                .where(activity_models.Activity.parent_activity_id == parent_id)
                .order_by(activity_models.Activity.start_time)
            )
            .scalars()
            .all()
        )
        legacy_in_order = (
            db.execute(
                select(activity_models.Activity.id)
                .where(activity_models.Activity.id.in_(legacy))
                .order_by(activity_models.Activity.start_time)
            )
            .scalars()
            .all()
        )
        assert len(legacy_in_order) == len(legs) > 1
        for activity_id in legacy_in_order:
            _degrade(db, activity_id)

        outcomes = [migration_service.reprocess_activity(activity_id, storage) for activity_id in legacy_in_order]

        assert set(outcomes) == {migration_service.ReprocessOutcome.REPROCESSED}
        for activity_id, leg_id in zip(legacy_in_order, legs, strict=True):
            assert _values(db, activity_id, _DERIVED) == _values(db, leg_id, _DERIVED)
            assert _children(db, activity_id) == _children(db, leg_id)
            assert _row(db, activity_id).parent_activity_id is None

    def test_a_multisport_activity_is_reprocessed_with_its_legs(self, db, owner, other, storage, tmp_path):
        [parent_id] = _import(db, owner.id, _TRIATHLON, tmp_path, storage)
        [expected_parent] = _import(db, other.id, _TRIATHLON, tmp_path, storage)

        def legs_of(activity_id: uuid.UUID) -> list[uuid.UUID]:
            db.expire_all()
            return list(
                db.execute(
                    select(activity_models.Activity.id)
                    .where(activity_models.Activity.parent_activity_id == activity_id)
                    .order_by(activity_models.Activity.start_time)
                ).scalars()
            )

        legs, expected_legs = legs_of(parent_id), legs_of(expected_parent)
        assert len(legs) == len(expected_legs) > 1
        edited = {"name": "Race day", "visibility": activity_constants.ActivityVisibility.PRIVATE.stored}
        db.execute(update(activity_models.Activity).where(activity_models.Activity.id.in_(legs)).values(**edited))
        for activity_id in (parent_id, *legs):
            _degrade(db, activity_id)

        outcome = migration_service.reprocess_activity(parent_id, storage)

        assert outcome is migration_service.ReprocessOutcome.REPROCESSED
        for activity_id, expected_id in zip((parent_id, *legs), (expected_parent, *expected_legs), strict=True):
            assert _values(db, activity_id, _DERIVED) == _values(db, expected_id, _DERIVED)
            assert _children(db, activity_id) == _children(db, expected_id)
            assert _row(db, activity_id).analysis_version == activities_computation.ANALYSIS_VERSION
        assert {_row(db, leg_id).name for leg_id in legs} == {"Race day"}

    def test_a_leg_has_no_file_of_its_own(self, db, owner, storage, tmp_path):
        [parent_id] = _import(db, owner.id, _TRIATHLON, tmp_path, storage)
        leg_id = (
            db.execute(
                select(activity_models.Activity.id).where(activity_models.Activity.parent_activity_id == parent_id)
            )
            .scalars()
            .first()
        )

        assert migration_service.reprocess_activity(leg_id, storage) is migration_service.ReprocessOutcome.NO_FILE

    def test_a_group_with_a_leg_the_file_lacks_changes_nothing(self, db, owner, storage, tmp_path):
        [parent_id] = _import(db, owner.id, _TRIATHLON, tmp_path, storage)
        leg_id = (
            db.execute(
                select(activity_models.Activity.id).where(activity_models.Activity.parent_activity_id == parent_id)
            )
            .scalars()
            .first()
        )
        _degrade(db, parent_id)
        db.execute(
            update(activity_models.Activity)
            .where(activity_models.Activity.id == leg_id)
            .values(start_time=_row(db, leg_id).start_time + timedelta(hours=5))
        )
        db.commit()
        before = (_values(db, parent_id, _DERIVED), _children(db, parent_id))

        outcome = migration_service.reprocess_activity(parent_id, storage)

        assert outcome is migration_service.ReprocessOutcome.NO_SESSION
        assert (_values(db, parent_id, _DERIVED), _children(db, parent_id)) == before
