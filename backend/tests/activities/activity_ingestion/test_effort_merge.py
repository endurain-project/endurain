"""An upload or sync of an effort the user has: it is merged into that activity, a better source rewrites it."""

import shutil
import uuid
from pathlib import Path

import pytest
from sqlalchemy import select, update
from sqlalchemy.orm import Session

import modules.activities.activity.constants as activity_constants
import modules.activities.activity.contracts as activity_contracts
import modules.activities.activity.events as activity_events
import modules.activities.activity.ingestion_service as ingestion_service
import modules.activities.activity.models as activity_models
import modules.activities.activity_file_storage.models as file_models
import modules.activities.activity_ingestion.contracts as ingestion_contracts
import modules.activities.activity_ingestion.pipeline_service as pipeline_service
import modules.activities.activity_streams.models as stream_models
from tests._factories.activities import make_parsed_activity
from tests._factories.reprocess import FIXTURES, RUN, TRIATHLON
from tests._factories.users import make_user

_RUN_TCX = FIXTURES / "outdoor_run" / "activity_24273515840.tcx"
_RUN_GPX = FIXTURES / "outdoor_run" / "activity_24273515840.gpx"
_DERIVED = (
    "distance",
    "end_time",
    "start_time",
    "total_elapsed_time",
    "total_timer_time",
    "average_hr",
    "max_hr",
    "calories",
    "tracker_manufacturer",
    "elevation_gain",
    "analysis_version",
)


@pytest.fixture
def owner(db: Session):
    user = make_user(db, timezone="UTC")
    db.commit()
    return user


@pytest.fixture
def created_events(platform) -> list:
    events: list = []
    platform.events.subscribe(activity_events.ACTIVITY_CREATED, events.append)
    return events


def _import(db: Session, user_id: uuid.UUID, path: Path, tmp_path: Path, storage, source=None):
    staged = tmp_path / f"{uuid.uuid4().hex}{path.suffix}"
    shutil.copyfile(path, staged)
    created = pipeline_service.validate_prepare_and_store_file(
        user_id, str(staged), db, source=source or ingestion_contracts.UploadSource(), storage=storage
    )
    db.commit()
    assert created
    return created


def _row(db: Session, activity_id: uuid.UUID) -> activity_models.Activity:
    db.expire_all()
    return db.execute(select(activity_models.Activity).where(activity_models.Activity.id == activity_id)).scalar_one()


def _kinds(db: Session, activity_id: uuid.UUID) -> list[tuple[str, int]]:
    return sorted((source.kind, source.precedence) for source in _row(db, activity_id).sources)


def _values(db: Session, activity_id: uuid.UUID) -> dict[str, object]:
    row = _row(db, activity_id)
    return {column: getattr(row, column) for column in _DERIVED}


def _file_rows(db: Session) -> list[file_models.ActivityFile]:
    return list(db.scalars(select(file_models.ActivityFile)))


def _count(db: Session) -> int:
    return len(db.scalars(select(activity_models.Activity.id)).all())


def _edit(db: Session, activity_id: uuid.UUID, **values: object) -> None:
    db.execute(update(activity_models.Activity).where(activity_models.Activity.id == activity_id).values(**values))
    db.commit()


class TestTheSameFileTwice:
    def test_the_second_upload_returns_the_first_activity_and_stores_nothing(
        self, db, owner, tmp_path, storage, created_events
    ):
        [first] = _import(db, owner.id, RUN, tmp_path, storage)

        [again] = _import(db, owner.id, RUN, tmp_path, storage)

        assert again.id == first.id
        assert _count(db) == 1
        assert len(_file_rows(db)) == 1
        assert len(created_events) == 1


class TestAWorseSourceArrivingLater:
    def test_a_tcx_after_a_fit_is_attached_and_the_activity_stays_as_it_was(
        self, db, owner, tmp_path, storage, created_events
    ):
        [fit] = _import(db, owner.id, RUN, tmp_path, storage)
        _edit(db, fit.id, name="Mine")
        before = _values(db, fit.id)
        file_before = _row(db, fit.id).file_id
        version_before = _row(db, fit.id).version

        [merged] = _import(db, owner.id, _RUN_TCX, tmp_path, storage)

        assert merged.id == fit.id
        assert _count(db) == 1
        assert _kinds(db, fit.id) == [("file", 1), ("file", 2)]
        assert _values(db, fit.id) == before
        assert (_row(db, fit.id).file_id, _row(db, fit.id).version) == (file_before, version_before)
        assert _row(db, fit.id).name == "Mine"
        assert [row.extension for row in _file_rows(db)] == [".fit"], "the weaker file is not retained"
        assert len(created_events) == 1

    def test_the_attached_file_is_recognised_when_it_comes_again(self, db, owner, tmp_path, storage):
        [fit] = _import(db, owner.id, RUN, tmp_path, storage)
        _import(db, owner.id, _RUN_TCX, tmp_path, storage)

        [again] = _import(db, owner.id, _RUN_TCX, tmp_path, storage)

        assert again.id == fit.id
        assert _count(db) == 1
        assert len(_row(db, fit.id).sources) == 2

    def test_a_gpx_after_a_tcx_ties_and_the_stored_recording_is_kept(self, db, owner, tmp_path, storage):
        [tcx] = _import(db, owner.id, _RUN_TCX, tmp_path, storage)
        before = _values(db, tcx.id)

        _import(db, owner.id, _RUN_GPX, tmp_path, storage)

        assert _count(db) == 1
        assert _values(db, tcx.id) == before
        assert _kinds(db, tcx.id) == [("file", 1), ("file", 1)]

    def test_the_same_fit_from_a_second_device_is_attached_with_its_own_source(self, db, owner, tmp_path, storage):
        [fit] = _import(db, owner.id, RUN, tmp_path, storage)
        before = _values(db, fit.id)

        [merged] = _import(
            db, owner.id, RUN, tmp_path, storage, source=ingestion_contracts.GarminSource(activity_id=9001)
        )

        assert merged.id == fit.id
        assert _count(db) == 1
        assert _kinds(db, fit.id) == [("file", 2), ("garmin", 2)]
        assert _values(db, fit.id) == before
        assert _row(db, fit.id).garminconnect_activity_id == 9001


class TestABetterSourceArrivingLater:
    def test_a_fit_after_a_tcx_recomputes_the_activity_in_place_and_keeps_what_the_owner_set(
        self, db, owner, tmp_path, storage, created_events
    ):
        other = make_user(db, timezone="UTC")
        db.commit()
        [expected] = _import(db, other.id, RUN, tmp_path, storage)
        [tcx] = _import(db, owner.id, _RUN_TCX, tmp_path, storage)
        _edit(db, tcx.id, name="Mine", description="My notes", visibility=2, hide_hr=True)
        version_before = _row(db, tcx.id).version
        tcx_file = _row(db, tcx.id).file_id

        [merged] = _import(db, owner.id, RUN, tmp_path, storage)

        assert merged.id == tcx.id
        assert _count(db) == 2
        row = _row(db, tcx.id)
        assert _values(db, tcx.id) == _values(db, expected.id)
        assert (row.name, row.description, row.visibility, row.hide_hr) == ("Mine", "My notes", 2, True)
        assert row.version == version_before, "a recompute from a file is no edit"
        assert _kinds(db, tcx.id) == [("file", 1), ("file", 2)]
        assert row.file_id != tcx_file
        assert sorted(file.extension for file in _file_rows(db)) == [".fit", ".fit"], "the TCX's row is gone"
        assert len(created_events) == 2, "the owner's activity and the other user's, no event for the recompute"
        samples = db.scalars(
            select(stream_models.ActivitySamples).where(stream_models.ActivitySamples.activity_id == tcx.id)
        ).all()
        assert len(samples) == 1

    def test_the_recomputed_activity_is_found_again_by_either_file(self, db, owner, tmp_path, storage):
        [tcx] = _import(db, owner.id, _RUN_TCX, tmp_path, storage)
        _import(db, owner.id, RUN, tmp_path, storage)

        assert _import(db, owner.id, RUN, tmp_path, storage)[0].id == tcx.id
        assert _import(db, owner.id, _RUN_TCX, tmp_path, storage)[0].id == tcx.id
        assert _count(db) == 1

    def test_a_fit_after_a_strava_activity_takes_the_files_name_and_description_and_moves_the_version(
        self, db, owner, tmp_path, storage, created_events
    ):
        other = make_user(db, timezone="UTC")
        db.commit()
        [expected] = _import(db, other.id, RUN, tmp_path, storage)
        expected_row = _row(db, expected.id)
        strava = ingestion_service.ingest(
            make_parsed_activity(
                owner.id,
                source=activity_contracts.ImportSource(kind="strava", provider_activity_id=4242, precedence=0),
                start=expected_row.start_time,
                end_time=expected_row.end_time,
                activity_type=activity_constants.ActivityType.RUN.stored,
                name="Strava's name",
                description="Strava's text",
                strava_activity_id=4242,
                calories=1,
            ),
            db,
        ).activity
        db.commit()
        _edit(db, strava.id, visibility=2, hide_map=True)
        version_before = _row(db, strava.id).version

        [merged] = _import(db, owner.id, RUN, tmp_path, storage)

        assert merged.id == strava.id
        assert _count(db) == 2
        row = _row(db, strava.id)
        assert (row.name, row.description) == (expected_row.name, expected_row.description)
        assert row.version == version_before + 1, "a stale client write must be refused"
        assert (row.visibility, row.hide_map) == (2, True)
        assert _values(db, strava.id) == _values(db, expected.id)
        assert _kinds(db, strava.id) == [("file", 2), ("strava", 0)]
        assert row.strava_activity_id == 4242
        assert row.file_id is not None
        assert len(created_events) == 2

    def test_a_tcx_after_a_strava_activity_also_takes_the_text(self, db, owner, tmp_path, storage):
        other = make_user(db, timezone="UTC")
        db.commit()
        [expected] = _import(db, other.id, _RUN_TCX, tmp_path, storage)
        expected_row = _row(db, expected.id)
        strava = ingestion_service.ingest(
            make_parsed_activity(
                owner.id,
                source=activity_contracts.ImportSource(kind="strava", provider_activity_id=4243, precedence=0),
                start=expected_row.start_time,
                end_time=expected_row.end_time,
                activity_type=activity_constants.ActivityType.RUN.stored,
                name="Strava's name",
                strava_activity_id=4243,
            ),
            db,
        ).activity
        db.commit()

        _import(db, owner.id, _RUN_TCX, tmp_path, storage)

        row = _row(db, strava.id)
        assert row.name == expected_row.name
        assert row.version == 2

    def test_an_activity_that_a_device_file_also_recorded_does_not_take_a_later_files_text(
        self, db, owner, tmp_path, storage
    ):
        [tcx] = _import(db, owner.id, _RUN_TCX, tmp_path, storage)
        ingestion_service.ingest(
            make_parsed_activity(
                owner.id,
                source=activity_contracts.ImportSource(kind="strava", provider_activity_id=4244, precedence=0),
                start=_row(db, tcx.id).start_time,
                end_time=_row(db, tcx.id).end_time,
                activity_type=activity_constants.ActivityType.RUN.stored,
                strava_activity_id=4244,
            ),
            db,
        )
        db.commit()
        _edit(db, tcx.id, name="Mine")
        version = _row(db, tcx.id).version

        _import(db, owner.id, RUN, tmp_path, storage)

        assert (_row(db, tcx.id).name, _row(db, tcx.id).version) == ("Mine", version)


class TestAMultisportFile:
    def test_the_same_file_from_garmin_is_attached_to_the_group_by_its_parent(self, db, owner, tmp_path, storage):
        [parent] = _import(db, owner.id, TRIATHLON, tmp_path, storage)
        rows_before = _count(db)

        [merged] = _import(
            db, owner.id, TRIATHLON, tmp_path, storage, source=ingestion_contracts.GarminSource(activity_id=777)
        )

        assert merged.id == parent.id
        assert _count(db) == rows_before
        assert _kinds(db, parent.id) == [("file", 2), ("garmin", 2)]
