"""Reprocessing one activity in place from its retained file: what it recomputes, what it must never touch."""

import hashlib
import json
import uuid
from datetime import timedelta
from pathlib import Path
from unittest.mock import MagicMock

import jasil.publisher as platform_publisher
import pytest
from sqlalchemy import delete, select, update
from sqlalchemy.orm import Session

import core.database as core_database
import core.exceptions as core_exceptions
import modules.activities.activity.audit_actions as activity_audit_actions
import modules.activities.activity.constants as activity_constants
import modules.activities.activity.crud as activity_crud
import modules.activities.activity.integration_service as activity_integration
import modules.activities.activity.models as activity_models
import modules.activities.activity_exercise_titles.models as exercise_title_models
import modules.activities.activity_file_storage.constants as file_storage_constants
import modules.activities.activity_file_storage.integration_service as file_storage
import modules.activities.activity_file_storage.models as file_models
import modules.activities.activity_ingestion.migration_service as migration_service
import modules.activities.activity_ingestion.pipeline_service as pipeline_service
import modules.activities.activity_laps.models as lap_models
import modules.activities.activity_sets.models as set_models
import modules.activities.activity_streams.constants as stream_constants
import modules.activities.activity_streams.models as stream_models
import modules.activities.activity_workout_steps.models as step_models
import modules.activities.computation as activities_computation
import modules.users.users.models as user_models
from tests._factories.activities import make_activity
from tests._factories.gears import make_gear
from tests._factories.ingestion import fit_file, retained_file, store_legacy_file
from tests._factories.reprocess import (
    BOGUS_DERIVED,
    OLD,
    RUN,
    STRENGTH,
    TREADMILL,
    TRIATHLON,
    degrade,
    import_fixture,
    import_legacy_legs,
    start_ordered,
)
from tests._factories.users import audit_rows_of, make_user

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
    "start_latitude",
    "start_longitude",
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


def _file_rows(db: Session) -> list[file_models.ActivityFile]:
    """Return the retained file rows, read in the test's own session."""
    db.expire_all()
    return list(db.scalars(select(file_models.ActivityFile)).all())


def _retained_ref(db: Session, activity_id: uuid.UUID):
    """Return the file row an activity references."""
    file_id = activity_integration.get_file_ids([activity_id], db)[activity_id]
    return file_storage.resolve_refs([file_id], db)[file_id]


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
        ("samples", stream_models.ActivitySamples),
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
    [activity_id] = import_fixture(db, user_id, source, tmp_path, storage)
    return activity_id


class TestReprocessingOneActivity:
    def test_recomputes_what_a_fresh_import_stores(self, db, owner, other, storage, tmp_path):
        [activity_id] = import_fixture(db, owner.id, RUN, tmp_path, storage)
        expected = _fresh(db, other.id, RUN, tmp_path, storage)
        degrade(db, activity_id)

        outcome = migration_service.reprocess_activity(activity_id, storage)

        assert outcome is migration_service.ReprocessOutcome.REPROCESSED
        assert _values(db, activity_id, _DERIVED) == _values(db, expected, _DERIVED)

    def test_replaces_streams_laps_sets_and_steps_exactly_once(self, db, owner, other, storage, tmp_path):
        [activity_id] = import_fixture(db, owner.id, STRENGTH, tmp_path, storage)
        expected = _children(db, _fresh(db, other.id, STRENGTH, tmp_path, storage))
        assert expected["sets"] and expected["steps"]
        degrade(db, activity_id)

        migration_service.reprocess_activity(activity_id, storage)

        assert _children(db, activity_id) == expected

    def test_replaces_the_children_of_a_run_with_a_track(self, db, owner, other, storage, tmp_path):
        [activity_id] = import_fixture(db, owner.id, RUN, tmp_path, storage)
        expected = _children(db, _fresh(db, other.id, RUN, tmp_path, storage))
        assert expected["samples"] and expected["laps"]
        assert expected["streams"] == []
        degrade(db, activity_id)

        migration_service.reprocess_activity(activity_id, storage)

        assert _children(db, activity_id) == expected

    def test_replaces_the_samples_and_rewrites_the_start_point_of_a_track(self, db, owner, other, storage, tmp_path):
        [activity_id] = import_fixture(db, owner.id, RUN, tmp_path, storage)
        expected = _children(db, _fresh(db, other.id, RUN, tmp_path, storage))["samples"]
        assert expected
        degrade(db, activity_id)
        assert _values(db, activity_id, ("start_latitude",)) == {"start_latitude": 1.0}

        migration_service.reprocess_activity(activity_id, storage)

        assert _children(db, activity_id)["samples"] == expected
        start = _values(db, activity_id, ("start_latitude", "start_longitude"))
        assert start["start_latitude"] != 1.0
        assert None not in start.values()

    def test_clears_the_start_point_of_an_indoor_activity(self, db, owner, storage, tmp_path):
        [activity_id] = import_fixture(db, owner.id, TREADMILL, tmp_path, storage)
        degrade(db, activity_id)

        migration_service.reprocess_activity(activity_id, storage)

        assert _values(db, activity_id, ("start_latitude", "start_longitude")) == {
            "start_latitude": None,
            "start_longitude": None,
        }

    def test_never_writes_what_the_owner_edited(self, db, owner, storage, tmp_path):
        [activity_id] = import_fixture(db, owner.id, RUN, tmp_path, storage)
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
        degrade(db, activity_id)
        before = _values(db, activity_id, _OWNED)

        migration_service.reprocess_activity(activity_id, storage)

        assert _values(db, activity_id, _OWNED) == before
        assert all(_values(db, activity_id, tuple(edits)).get(field) == value for field, value in edits.items())

    def test_keeps_the_version_and_stamps_the_analysis_version_and_updated_at(self, db, owner, storage, tmp_path):
        [activity_id] = import_fixture(db, owner.id, RUN, tmp_path, storage)
        degrade(db, activity_id)
        before = _row(db, activity_id)
        version = before.version
        assert before.analysis_version == 0

        migration_service.reprocess_activity(activity_id, storage)

        after = _row(db, activity_id)
        assert after.version == version
        assert after.analysis_version == activities_computation.ANALYSIS_VERSION
        assert after.updated_at > OLD

    def test_a_walk_that_read_the_old_file_cannot_overwrite_what_a_recompute_wrote_meanwhile(
        self, db, owner, storage, tmp_path, monkeypatch
    ):
        [activity_id] = import_fixture(db, owner.id, RUN, tmp_path, storage)
        degrade(db, activity_id)
        old_file = _row(db, activity_id).file_id
        parse = pipeline_service.parse_file

        def parse_while_a_better_source_recomputes(*args, **kwargs):
            parsed = parse(*args, **kwargs)
            staged = file_storage.stage_file(owner.id, "9" * 64, ".fit", b"better", storage)
            with core_database.SessionLocal() as other_session:
                assert activity_integration.replace_file_id(activity_id, old_file, staged.ref.file_id, other_session)
                other_session.execute(
                    update(activity_models.Activity)
                    .where(activity_models.Activity.id == activity_id)
                    .values(distance=424242, analysis_version=activities_computation.ANALYSIS_VERSION)
                )
                other_session.commit()
            return parsed

        monkeypatch.setattr(pipeline_service, "parse_file", parse_while_a_better_source_recomputes)

        outcome = migration_service.reprocess_activity(activity_id, storage)

        assert outcome is migration_service.ReprocessOutcome.NO_FILE
        row = _row(db, activity_id)
        assert row.distance == 424242, "the walk's values from the old file were not written"
        assert row.file_id != old_file

    def test_a_walk_over_an_activity_with_no_file_row_writes_while_it_still_has_none(
        self, db, owner, storage, tmp_path, monkeypatch
    ):
        [activity_id] = import_fixture(db, owner.id, RUN, tmp_path, storage)
        degrade(db, activity_id)
        db.execute(
            update(activity_models.Activity).where(activity_models.Activity.id == activity_id).values(file_id=None)
        )
        db.commit()
        data = retained_file(activity_id, storage)
        if data is None:
            store_legacy_file(activity_id, RUN.read_bytes(), storage)

        outcome = migration_service.reprocess_activity(activity_id, storage)

        assert outcome is migration_service.ReprocessOutcome.REPROCESSED

    def test_is_idempotent(self, db, owner, storage, tmp_path):
        [activity_id] = import_fixture(db, owner.id, STRENGTH, tmp_path, storage)
        degrade(db, activity_id)

        migration_service.reprocess_activity(activity_id, storage)
        once = (_values(db, activity_id, _DERIVED), _children(db, activity_id))
        outcome = migration_service.reprocess_activity(activity_id, storage)

        assert outcome is migration_service.ReprocessOutcome.REPROCESSED
        assert (_values(db, activity_id, _DERIVED), _children(db, activity_id)) == once

    def test_publishes_no_event(self, db, owner, storage, tmp_path, published):
        [activity_id] = import_fixture(db, owner.id, RUN, tmp_path, storage)
        published.reset_mock()
        degrade(db, activity_id)

        migration_service.reprocess_activity(activity_id, storage)

        published.assert_not_called()

    def test_an_activity_stored_without_a_zone_takes_the_owners_timezone(self, db, storage, tmp_path):
        tokyo = make_user(db, timezone="Asia/Tokyo")
        db.commit()
        without_a_zone = tmp_path / "no_gps.fit"
        without_a_zone.write_bytes(fit_file(with_gps=False))
        [activity_id] = import_fixture(db, tokyo.id, without_a_zone, tmp_path, storage)
        degrade(db, activity_id)
        _store_timezone(db, activity_id, None)

        migration_service.reprocess_activity(activity_id, storage)

        assert _row(db, activity_id).timezone == "Asia/Tokyo"

    def test_a_file_without_a_zone_keeps_the_zone_it_was_imported_in_after_the_owner_moves(self, db, storage, tmp_path):
        traveller = make_user(db, timezone="Asia/Tokyo")
        db.commit()
        without_a_zone = tmp_path / "no_gps.fit"
        without_a_zone.write_bytes(fit_file(with_gps=False))
        [activity_id] = import_fixture(db, traveller.id, without_a_zone, tmp_path, storage)
        degrade(db, activity_id)
        # An old row holds the zone it was imported in; the owner moved since.
        _store_timezone(db, activity_id, "Asia/Tokyo")
        db.execute(
            update(user_models.Users).where(user_models.Users.id == traveller.id).values(timezone="Europe/Lisbon")
        )
        db.commit()

        migration_service.reprocess_activity(activity_id, storage)

        assert _row(db, activity_id).timezone == "Asia/Tokyo"

    def test_re_adds_the_exercise_titles_of_the_file(self, db, owner, storage, tmp_path):
        [activity_id] = import_fixture(db, owner.id, STRENGTH, tmp_path, storage)
        stored = db.execute(select(exercise_title_models.ActivityExerciseTitles)).scalars().all()
        assert stored
        db.execute(delete(exercise_title_models.ActivityExerciseTitles))
        degrade(db, activity_id)

        migration_service.reprocess_activity(activity_id, storage)

        assert len(db.execute(select(exercise_title_models.ActivityExerciseTitles)).scalars().all()) == len(stored)

    def test_leaves_another_users_activity_alone(self, db, owner, other, storage, tmp_path):
        [activity_id] = import_fixture(db, owner.id, RUN, tmp_path, storage)
        neighbour = _fresh(db, other.id, RUN, tmp_path, storage)
        degrade(db, activity_id)
        degrade(db, neighbour)
        before = (_values(db, neighbour, _DERIVED), _children(db, neighbour), _row(db, neighbour).analysis_version)

        migration_service.reprocess_activity(activity_id, storage)

        assert (
            _values(db, neighbour, _DERIVED),
            _children(db, neighbour),
            _row(db, neighbour).analysis_version,
        ) == before


class TestTheThumbnail:
    def _samples(self, db: Session, activity_id: uuid.UUID) -> stream_models.ActivitySamples:
        db.expire_all()
        return db.execute(
            select(stream_models.ActivitySamples).where(stream_models.ActivitySamples.activity_id == activity_id)
        ).scalar_one()

    def _as_old_streams(self, db: Session, activity_id: uuid.UUID, *, shift: float = 0.0) -> None:
        """Store the track the way an activity stored before v0.22 has it: an old map stream and no samples row."""
        samples = self._samples(db, activity_id)
        start = _row(db, activity_id).start_time
        db.add(
            stream_models.ActivityStreams(
                activity_id=activity_id,
                stream_type=stream_constants.STREAM_TYPE_MAP,
                stream_waypoints=[
                    {
                        "time": (start + timedelta(milliseconds=offset)).strftime("%Y-%m-%dT%H:%M:%S"),
                        "lat": lat + shift,
                        "lon": lon,
                    }
                    for offset, lat, lon in zip(samples.offsets_ms, samples.latitude, samples.longitude, strict=True)
                    if lat is not None and lon is not None
                ],
            )
        )
        db.delete(samples)
        db.commit()

    def _set_key(self, db: Session, activity_id: uuid.UUID, key: str | None) -> None:
        db.execute(
            update(activity_models.Activity)
            .where(activity_models.Activity.id == activity_id)
            .values(map_thumbnail_path=key)
        )
        db.commit()

    def test_is_kept_when_the_track_is_the_same(self, db, owner, storage, tmp_path):
        [activity_id] = import_fixture(db, owner.id, RUN, tmp_path, storage)
        self._set_key(db, activity_id, f"{activity_id}.webp")
        db.execute(
            update(activity_models.Activity)
            .where(activity_models.Activity.id == activity_id)
            .values(**BOGUS_DERIVED, analysis_version=0)
        )
        db.commit()

        migration_service.reprocess_activity(activity_id, storage)

        assert _row(db, activity_id).map_thumbnail_path == f"{activity_id}.webp"

    def test_is_cleared_when_the_track_changed(self, db, owner, storage, tmp_path):
        [activity_id] = import_fixture(db, owner.id, RUN, tmp_path, storage)
        self._set_key(db, activity_id, f"{activity_id}.webp")
        samples = self._samples(db, activity_id)
        samples.latitude = [None if lat is None else lat + 1 for lat in samples.latitude]
        db.commit()

        migration_service.reprocess_activity(activity_id, storage)

        assert _row(db, activity_id).map_thumbnail_path is None

    def test_is_cleared_when_an_activity_with_only_old_streams_gets_another_track(self, db, owner, storage, tmp_path):
        [activity_id] = import_fixture(db, owner.id, RUN, tmp_path, storage)
        self._as_old_streams(db, activity_id, shift=1.0)
        self._set_key(db, activity_id, f"{activity_id}.webp")

        migration_service.reprocess_activity(activity_id, storage)

        assert _row(db, activity_id).map_thumbnail_path is None

    def test_is_kept_when_the_old_streams_hold_the_track_the_reprocess_stores(self, db, owner, storage, tmp_path):
        [activity_id] = import_fixture(db, owner.id, RUN, tmp_path, storage)
        self._as_old_streams(db, activity_id)
        self._set_key(db, activity_id, f"{activity_id}.webp")

        migration_service.reprocess_activity(activity_id, storage)

        assert _row(db, activity_id).map_thumbnail_path == f"{activity_id}.webp"
        assert self._samples(db, activity_id).latitude is not None

    def test_is_kept_for_an_activity_with_no_track(self, db, owner, storage, tmp_path):
        [activity_id] = import_fixture(db, owner.id, TREADMILL, tmp_path, storage)
        self._set_key(db, activity_id, f"{activity_id}.webp")

        migration_service.reprocess_activity(activity_id, storage)

        assert _row(db, activity_id).map_thumbnail_path == f"{activity_id}.webp"


class TestWhenNothingCanBeReprocessed:
    def test_an_activity_without_a_retained_file_is_left_as_it_is(self, db, owner, storage, tmp_path):
        [activity_id] = import_fixture(db, owner.id, RUN, tmp_path, storage)
        degrade(db, activity_id)
        storage.delete(file_storage_constants.ACTIVITY_FILE_STORAGE_AREA, _retained_ref(db, activity_id).storage_key)
        before = (_values(db, activity_id, _DERIVED), _children(db, activity_id))

        outcome = migration_service.reprocess_activity(activity_id, storage)

        assert outcome is migration_service.ReprocessOutcome.NO_FILE
        assert (_values(db, activity_id, _DERIVED), _children(db, activity_id)) == before
        assert _row(db, activity_id).analysis_version == 0

    def test_an_unknown_activity_has_no_file(self, db, storage):
        assert migration_service.reprocess_activity(uuid.uuid4(), storage) is migration_service.ReprocessOutcome.NO_FILE

    def test_a_corrupted_file_fails_and_changes_nothing(self, db, owner, storage, tmp_path, caplog):
        [activity_id] = import_fixture(db, owner.id, RUN, tmp_path, storage)
        degrade(db, activity_id)
        storage.save(
            file_storage_constants.ACTIVITY_FILE_STORAGE_AREA,
            _retained_ref(db, activity_id).storage_key,
            b"this is not a fit file at all",
        )
        before = (_values(db, activity_id, _DERIVED), _children(db, activity_id))

        outcome = migration_service.reprocess_activity(activity_id, storage)

        assert outcome is migration_service.ReprocessOutcome.FAILED
        assert (_values(db, activity_id, _DERIVED), _children(db, activity_id)) == before
        assert _row(db, activity_id).analysis_version == 0
        assert _logged(caplog, activity_id)

    def test_a_parse_refusal_fails(self, db, owner, storage, tmp_path, monkeypatch):
        [activity_id] = import_fixture(db, owner.id, RUN, tmp_path, storage)

        def refuse(*_args, **_kwargs):
            raise core_exceptions.InvalidInputError("no")

        monkeypatch.setattr(pipeline_service, "parse_file", refuse)

        assert migration_service.reprocess_activity(activity_id, storage) is migration_service.ReprocessOutcome.FAILED

    def test_a_file_with_no_session_at_the_start_has_no_session(self, db, owner, storage, tmp_path, caplog):
        [activity_id] = import_fixture(db, owner.id, RUN, tmp_path, storage)
        degrade(db, activity_id)
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
        [activity_id] = import_fixture(db, owner.id, RUN, tmp_path, storage)
        degrade(db, activity_id)
        db.execute(
            update(activity_models.Activity)
            .where(activity_models.Activity.id == activity_id)
            .values(start_time=_row(db, activity_id).start_time - timedelta(milliseconds=900))
        )
        db.commit()

        outcome = migration_service.reprocess_activity(activity_id, storage)

        assert outcome is migration_service.ReprocessOutcome.REPROCESSED


class TestAMultiSessionFile:
    def test_a_legacy_leg_whose_siblings_are_missing_is_reprocessed_alone_from_its_session(
        self, db, owner, other, storage, tmp_path, monkeypatch
    ):
        legacy = import_legacy_legs(db, owner.id, TRIATHLON, tmp_path, storage, monkeypatch)
        [parent_id] = import_fixture(db, other.id, TRIATHLON, tmp_path, storage)
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
        missing = legacy_in_order.pop()
        file_storage.delete_legacy_activity_file(missing, storage)
        db.execute(delete(activity_models.Activity).where(activity_models.Activity.id == missing))
        db.commit()
        for activity_id in legacy_in_order:
            degrade(db, activity_id)

        outcomes = [migration_service.reprocess_activity(activity_id, storage) for activity_id in legacy_in_order]

        assert set(outcomes) == {migration_service.ReprocessOutcome.REPROCESSED}
        for activity_id, leg_id in zip(legacy_in_order, legs[:-1], strict=True):
            assert _values(db, activity_id, _DERIVED) == _values(db, leg_id, _DERIVED)
            assert _children(db, activity_id) == _children(db, leg_id)
            assert _row(db, activity_id).parent_activity_id is None
            assert retained_file(activity_id, storage) is not None

    def test_a_multisport_activity_is_reprocessed_with_its_legs(self, db, owner, other, storage, tmp_path):
        [parent_id] = import_fixture(db, owner.id, TRIATHLON, tmp_path, storage)
        [expected_parent] = import_fixture(db, other.id, TRIATHLON, tmp_path, storage)

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
            degrade(db, activity_id)

        outcome = migration_service.reprocess_activity(parent_id, storage)

        assert outcome is migration_service.ReprocessOutcome.REPROCESSED
        for activity_id, expected_id in zip((parent_id, *legs), (expected_parent, *expected_legs), strict=True):
            assert _values(db, activity_id, _DERIVED) == _values(db, expected_id, _DERIVED)
            assert _children(db, activity_id) == _children(db, expected_id)
            assert _row(db, activity_id).analysis_version == activities_computation.ANALYSIS_VERSION
        assert {_row(db, leg_id).name for leg_id in legs} == {"Race day"}

    def test_a_leg_has_no_file_of_its_own(self, db, owner, storage, tmp_path):
        [parent_id] = import_fixture(db, owner.id, TRIATHLON, tmp_path, storage)
        leg_id = (
            db.execute(
                select(activity_models.Activity.id).where(activity_models.Activity.parent_activity_id == parent_id)
            )
            .scalars()
            .first()
        )

        assert migration_service.reprocess_activity(leg_id, storage) is migration_service.ReprocessOutcome.NO_FILE

    def test_a_group_with_a_leg_the_file_lacks_changes_nothing(self, db, owner, storage, tmp_path):
        [parent_id] = import_fixture(db, owner.id, TRIATHLON, tmp_path, storage)
        leg_id = (
            db.execute(
                select(activity_models.Activity.id).where(activity_models.Activity.parent_activity_id == parent_id)
            )
            .scalars()
            .first()
        )
        degrade(db, parent_id)
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


_VISIBILITY = activity_constants.ActivityVisibility
_HIDE_FLAGS = ("hide_hr", "hide_map", "hide_gear")


def _legs_of(db: Session, parent_id: uuid.UUID) -> list[uuid.UUID]:
    """Return a parent's legs in start order."""
    db.expire_all()
    return list(
        db.execute(
            select(activity_models.Activity.id)
            .where(activity_models.Activity.parent_activity_id == parent_id)
            .order_by(activity_models.Activity.start_time)
        ).scalars()
    )


def _legacy_group(db: Session, user_id: uuid.UUID, tmp_path: Path, storage, monkeypatch) -> list[uuid.UUID]:
    """Return the five legacy legs of the triathlon, in start order."""
    return start_ordered(db, import_legacy_legs(db, user_id, TRIATHLON, tmp_path, storage, monkeypatch))


def _parent_of(db: Session, leg_id: uuid.UUID) -> uuid.UUID | None:
    return _row(db, leg_id).parent_activity_id


def _set(db: Session, activity_ids: list[uuid.UUID], **values: object) -> None:
    db.execute(update(activity_models.Activity).where(activity_models.Activity.id.in_(activity_ids)).values(**values))
    db.commit()


def _sources_of(db: Session, activity_id: uuid.UUID) -> list[tuple[str, int | None, str | None, bool]]:
    """Return an activity's sources as ``(kind, provider id, file hash, has a start)``."""
    rows = db.scalars(
        select(activity_models.ActivitySource).where(activity_models.ActivitySource.activity_id == activity_id)
    ).all()
    return sorted((row.kind, row.provider_id, row.file_sha256, row.session_start is not None) for row in rows)


def _replace_sources(db: Session, activity_id: uuid.UUID, user_id: uuid.UUID, *sources: dict[str, object]) -> None:
    """Give an activity exactly the given sources."""
    db.execute(delete(activity_models.ActivitySource).where(activity_models.ActivitySource.activity_id == activity_id))
    for source in sources:
        db.add(activity_models.ActivitySource(activity_id=activity_id, user_id=user_id, precedence=2, **source))
    db.commit()


def _all_columns(db: Session, activity_id: uuid.UUID) -> dict[str, object]:
    row = _row(db, activity_id)
    return {column.key: getattr(row, column.key) for column in activity_models.Activity.__table__.columns}


_SHA = hashlib.sha256(TRIATHLON.read_bytes()).hexdigest()


class TestRegroupingLegacyLegs:
    def test_the_legs_end_under_one_multisport_parent_with_a_fresh_imports_totals(
        self, db, owner, other, storage, tmp_path, monkeypatch
    ):
        legs = _legacy_group(db, owner.id, tmp_path, storage, monkeypatch)
        [expected_id] = import_fixture(db, other.id, TRIATHLON, tmp_path, storage)
        expected_legs = _legs_of(db, expected_id)
        assert len(legs) == len(expected_legs) > 1

        outcome = migration_service.reprocess_activity(legs[2], storage)

        assert outcome is migration_service.ReprocessOutcome.REPROCESSED
        parent_id = _parent_of(db, legs[0])
        assert parent_id is not None
        assert {_parent_of(db, leg) for leg in legs} == {parent_id}
        parent = _row(db, parent_id)
        assert parent.parent_activity_id is None
        assert parent.activity_type == activity_constants.ActivityType.MULTISPORT.stored
        assert parent.user_id == owner.id
        assert parent.analysis_version == activities_computation.ANALYSIS_VERSION
        assert _sources_of(db, parent_id) == [("file", None, _SHA, False)]
        assert parent.map_thumbnail_path is None
        assert parent.gear_id is None
        assert _values(db, parent_id, _DERIVED) == _values(db, expected_id, _DERIVED)
        assert _children(db, parent_id) == _children(db, expected_id)
        for leg, expected_leg in zip(legs, expected_legs, strict=True):
            assert _values(db, leg, _DERIVED) == _values(db, expected_leg, _DERIVED)
            assert _children(db, leg) == _children(db, expected_leg)
            assert _row(db, leg).analysis_version == activities_computation.ANALYSIS_VERSION
            assert _sources_of(db, leg) == [("file", None, _SHA, True)]

    def test_the_list_shows_the_parent_and_not_the_legs(self, db, owner, storage, tmp_path, monkeypatch):
        legs = _legacy_group(db, owner.id, tmp_path, storage, monkeypatch)

        migration_service.reprocess_activity(legs[0], storage)

        listed = activity_crud.get_user_activities_with_pagination(owner.id, db, user_is_owner=True)
        assert [activity.id for activity in listed] == [_parent_of(db, legs[0])]
        with_legs = activity_crud.get_user_activities_with_pagination(
            owner.id, db, user_is_owner=True, include_legs=True
        )
        assert {activity.id for activity in with_legs} == {_parent_of(db, legs[0]), *legs}

    def test_the_most_private_combination_is_applied_to_the_parent_and_every_leg(
        self, db, owner, storage, tmp_path, monkeypatch
    ):
        legs = _legacy_group(db, owner.id, tmp_path, storage, monkeypatch)
        _set(db, [legs[0]], visibility=_VISIBILITY.PUBLIC.stored, hide_hr=True)
        _set(db, [legs[1]], visibility=_VISIBILITY.FOLLOWERS.stored, hide_map=True)
        _set(db, [legs[2]], visibility=_VISIBILITY.PUBLIC.stored, is_hidden=True)
        _set(db, [legs[3]], visibility=_VISIBILITY.PUBLIC.stored, hide_gear=True)
        _set(db, [legs[4]], visibility=_VISIBILITY.PUBLIC.stored)

        migration_service.reprocess_activity(legs[0], storage)

        parent_id = _parent_of(db, legs[0])
        assert parent_id is not None
        for activity_id in (parent_id, *legs):
            row = _row(db, activity_id)
            assert row.visibility == _VISIBILITY.FOLLOWERS.stored
            assert row.is_hidden is True
            assert {flag for flag in activity_constants.PRIVACY_FIELDS if getattr(row, flag) is True} == {
                "is_hidden",
                *_HIDE_FLAGS,
            }

    def test_each_leg_whose_visibility_changed_gets_one_audit_row_without_values(
        self, db, owner, storage, tmp_path, monkeypatch
    ):
        legs = _legacy_group(db, owner.id, tmp_path, storage, monkeypatch)
        _set(db, legs, visibility=_VISIBILITY.PRIVATE.stored)
        _set(db, [legs[1]], visibility=_VISIBILITY.PUBLIC.stored, hide_hr=True)
        _set(db, [legs[3]], hide_map=True)

        migration_service.reprocess_activity(legs[0], storage)

        rows = audit_rows_of(db, activity_audit_actions.VISIBILITY_UPDATE.id)
        details = {row.target_id: sorted(row.details["changed_fields"]) for row in rows}
        assert len(rows) == len(details)
        assert details == {
            str(legs[0]): ["hide_hr", "hide_map"],
            str(legs[1]): ["hide_map", "visibility"],
            str(legs[2]): ["hide_hr", "hide_map"],
            str(legs[3]): ["hide_hr"],
            str(legs[4]): ["hide_hr", "hide_map"],
        }
        assert {row.target_owner_id for row in rows} == {str(owner.id)}
        assert {row.target_type for row in rows} == {"activity"}

    def test_a_leg_with_nothing_to_change_in_privacy_has_no_audit_row(self, db, owner, storage, tmp_path, monkeypatch):
        legs = _legacy_group(db, owner.id, tmp_path, storage, monkeypatch)
        _set(db, legs, visibility=_VISIBILITY.FOLLOWERS.stored)

        migration_service.reprocess_activity(legs[0], storage)

        assert audit_rows_of(db, activity_audit_actions.VISIBILITY_UPDATE.id) == []

    def test_leg_names_notes_types_and_gear_are_kept(self, db, owner, storage, tmp_path, monkeypatch):
        legs = _legacy_group(db, owner.id, tmp_path, storage, monkeypatch)
        gear = make_gear(db, owner.id)
        db.commit()
        for index, leg in enumerate(legs):
            _set(
                db,
                [leg],
                name=f"Leg {index}",
                description=f"About {index}",
                private_notes=f"Note {index}",
                gear_id=gear.id if index == 1 else None,
            )
        before = {
            leg: _values(db, leg, ("name", "description", "private_notes", "activity_type", "gear_id")) for leg in legs
        }

        migration_service.reprocess_activity(legs[0], storage)

        for leg in legs:
            assert _values(db, leg, ("name", "description", "private_notes", "activity_type", "gear_id")) == before[leg]

    def test_the_parent_takes_the_name_and_description_the_legs_share(self, db, owner, storage, tmp_path, monkeypatch):
        legs = _legacy_group(db, owner.id, tmp_path, storage, monkeypatch)
        _set(db, legs, name="Race day", description="Sunny")

        migration_service.reprocess_activity(legs[0], storage)

        parent = _row(db, _parent_of(db, legs[0]))
        assert (parent.name, parent.description) == ("Race day", "Sunny")

    def test_the_parent_takes_the_files_name_when_the_legs_differ(
        self, db, owner, other, storage, tmp_path, monkeypatch
    ):
        legs = _legacy_group(db, owner.id, tmp_path, storage, monkeypatch)
        [expected_id] = import_fixture(db, other.id, TRIATHLON, tmp_path, storage)
        _set(db, [legs[0]], name="First", description="One")
        _set(db, [legs[1]], name="Second", description="Two")

        migration_service.reprocess_activity(legs[0], storage)

        parent = _row(db, _parent_of(db, legs[0]))
        expected = _row(db, expected_id)
        assert (parent.name, parent.description) == (expected.name, expected.description)

    def test_a_leg_changed_in_parent_or_privacy_has_its_version_bumped_and_updated_at_stamped(
        self, db, owner, storage, tmp_path, monkeypatch
    ):
        legs = _legacy_group(db, owner.id, tmp_path, storage, monkeypatch)
        _set(db, legs, updated_at=OLD)
        versions = {leg: _row(db, leg).version for leg in legs}

        migration_service.reprocess_activity(legs[0], storage)

        for leg in legs:
            assert _row(db, leg).version > versions[leg]
            assert _row(db, leg).updated_at > OLD

    def test_the_file_is_kept_once_under_the_parent(self, db, owner, storage, tmp_path, monkeypatch):
        legs = _legacy_group(db, owner.id, tmp_path, storage, monkeypatch)
        assert all(retained_file(leg, storage) is not None for leg in legs)

        migration_service.reprocess_activity(legs[3], storage)

        parent_id = _parent_of(db, legs[0])
        assert parent_id is not None
        stored = retained_file(parent_id, storage)
        assert stored is not None
        assert stored[0] == ".fit"
        assert stored[1] == TRIATHLON.read_bytes()
        assert all(retained_file(leg, storage) is None for leg in legs)

    def test_the_parent_file_is_staged_before_the_group_commits_and_attached_with_it(
        self, db, owner, storage, tmp_path, monkeypatch
    ):
        legs = _legacy_group(db, owner.id, tmp_path, storage, monkeypatch)
        real = file_storage.stage_file
        seen: list[int] = []

        def recording(*args, **kwargs):
            db.expire_all()
            parents = db.execute(
                select(activity_models.Activity.id).where(
                    activity_models.Activity.activity_type == activity_constants.ActivityType.MULTISPORT.stored
                )
            ).all()
            seen.append(len(parents))
            return real(*args, **kwargs)

        monkeypatch.setattr(file_storage, "stage_file", recording)

        migration_service.reprocess_activity(legs[0], storage)

        assert seen == [0]
        parent_id = _parent_of(db, legs[0])
        assert parent_id is not None
        [row] = _file_rows(db)
        assert (_row(db, parent_id).file_id, row.state) == (row.id, file_storage_constants.ActivityFileState.ATTACHED)

    def test_a_transaction_that_raises_leaves_no_parent_and_no_staged_file(
        self, db, owner, storage, tmp_path, monkeypatch
    ):
        legs = _legacy_group(db, owner.id, tmp_path, storage, monkeypatch)

        def boom(*args, **kwargs):
            raise RuntimeError("database is down")

        monkeypatch.setattr(activity_integration, "regroup_legs", boom)

        with pytest.raises(RuntimeError, match="database is down"):
            migration_service.reprocess_activity(legs[0], storage)

        assert _file_rows(db) == []
        assert list(storage.list_keys(file_storage_constants.ACTIVITY_FILE_STORAGE_AREA, "files/")) == []
        assert {_parent_of(db, leg) for leg in legs} == {None}
        assert all(retained_file(leg, storage) is not None for leg in legs)

    def test_a_regroup_that_stages_nothing_removes_the_staged_file(self, db, owner, storage, tmp_path, monkeypatch):
        legs = _legacy_group(db, owner.id, tmp_path, storage, monkeypatch)
        taken = make_activity(db, owner.id, start_time=OLD, end_time=OLD + timedelta(hours=1))
        _replace_sources(db, taken.id, owner.id, {"kind": "file", "file_sha256": _SHA})

        outcome = migration_service.reprocess_activity(legs[0], storage)

        assert outcome is migration_service.ReprocessOutcome.REPROCESSED
        # No parent row was left; the leg that was reprocessed alone adopted its own file instead.
        [row] = _file_rows(db)
        assert row.storage_key == f"processed/{legs[0]}.fit"
        assert list(storage.list_keys(file_storage_constants.ACTIVITY_FILE_STORAGE_AREA, "files/")) == []
        assert all(retained_file(leg, storage) is not None for leg in legs)

    def test_a_second_run_changes_nothing_on_a_leg_or_the_parent(self, db, owner, storage, tmp_path, monkeypatch):
        legs = _legacy_group(db, owner.id, tmp_path, storage, monkeypatch)
        migration_service.reprocess_activity(legs[0], storage)
        parent_id = _parent_of(db, legs[0])
        assert parent_id is not None
        everything = (parent_id, *legs)
        before = {activity_id: _all_columns(db, activity_id) for activity_id in everything}
        children = {activity_id: _children(db, activity_id) for activity_id in everything}
        ids_before = set(db.execute(select(activity_models.Activity.id)).scalars())

        for leg in legs:
            migration_service.reprocess_activity(leg, storage)
        parent_outcome = migration_service.reprocess_activity(parent_id, storage)

        assert parent_outcome is migration_service.ReprocessOutcome.REPROCESSED
        after = {activity_id: _all_columns(db, activity_id) for activity_id in everything}
        for activity_id in everything:
            assert {k: v for k, v in after[activity_id].items() if k != "updated_at"} == {
                k: v for k, v in before[activity_id].items() if k != "updated_at"
            }
            assert _children(db, activity_id) == children[activity_id]
        assert set(db.execute(select(activity_models.Activity.id)).scalars()) == ids_before

    def test_profile_restored_legs_without_a_source_regroup_by_the_file_hash(
        self, db, owner, storage, tmp_path, monkeypatch
    ):
        legs = _legacy_group(db, owner.id, tmp_path, storage, monkeypatch)
        for leg in legs:
            _replace_sources(db, leg, owner.id)

        outcome = migration_service.reprocess_activity(legs[1], storage)

        assert outcome is migration_service.ReprocessOutcome.REPROCESSED
        parent_id = _parent_of(db, legs[0])
        assert parent_id is not None
        assert {_parent_of(db, leg) for leg in legs} == {parent_id}
        assert _sources_of(db, parent_id) == [("file", None, _SHA, False)]

    def test_a_garmin_legacy_group_gets_the_garmin_source_and_id(self, db, owner, storage, tmp_path, monkeypatch):
        legs = _legacy_group(db, owner.id, tmp_path, storage, monkeypatch)
        for leg in legs:
            _replace_sources(
                db,
                leg,
                owner.id,
                {"kind": "garmin", "provider_id": 987654321, "session_start": _row(db, leg).start_time},
            )

        migration_service.reprocess_activity(legs[0], storage)

        parent = _row(db, _parent_of(db, legs[0]))
        assert _sources_of(db, parent.id) == [("garmin", 987654321, None, False)]
        assert parent.garminconnect_activity_id == 987654321

    def test_a_different_file_with_the_same_start_times_is_not_grouped(self, db, owner, storage, tmp_path, monkeypatch):
        legs = _legacy_group(db, owner.id, tmp_path, storage, monkeypatch)
        store_legacy_file(legs[3], b"another recording", storage)

        outcome = migration_service.reprocess_activity(legs[0], storage)

        assert outcome is migration_service.ReprocessOutcome.REPROCESSED
        assert {_parent_of(db, leg) for leg in legs} == {None}
        assert all(retained_file(leg, storage) is not None for leg in legs)

    def test_another_users_activity_with_the_same_file_is_not_a_sibling(
        self, db, owner, other, storage, tmp_path, monkeypatch
    ):
        legs = _legacy_group(db, owner.id, tmp_path, storage, monkeypatch)
        others = _legacy_group(db, other.id, tmp_path, storage, monkeypatch)

        migration_service.reprocess_activity(legs[0], storage)

        parent_id = _parent_of(db, legs[0])
        assert {_parent_of(db, leg) for leg in legs} == {parent_id}
        assert {_parent_of(db, leg) for leg in others} == {None}

    def test_a_parent_key_that_is_already_stored_means_no_regroup(self, db, owner, storage, tmp_path, monkeypatch):
        legs = _legacy_group(db, owner.id, tmp_path, storage, monkeypatch)
        taken = make_activity(db, owner.id, start_time=OLD, end_time=OLD + timedelta(hours=1))
        _replace_sources(db, taken.id, owner.id, {"kind": "file", "file_sha256": _SHA})

        outcome = migration_service.reprocess_activity(legs[0], storage)

        assert outcome is migration_service.ReprocessOutcome.REPROCESSED
        assert {_parent_of(db, leg) for leg in legs} == {None}

    def test_publishes_no_event(self, db, owner, storage, tmp_path, monkeypatch, published):
        legs = _legacy_group(db, owner.id, tmp_path, storage, monkeypatch)
        published.reset_mock()

        migration_service.reprocess_activity(legs[0], storage)

        published.assert_not_called()
