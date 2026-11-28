"""The reprocess walk leaves no visited activity in the storage layout of an earlier release.

An activity's file stored before file rows existed is adopted into a row at the key it has, its file source takes the
precedence of the file's format, and an activity the reprocess did not rewrite has its old streams converted to samples.
"""

import gzip
import hashlib
import uuid
from datetime import timedelta
from pathlib import Path

import jasil.events as platform_events
import pytest
from sqlalchemy import delete, select, update
from sqlalchemy.orm import Session

import core.database as core_database
import migrations.activity_reprocess as reprocess_job
import modules.activities.activity.constants as activity_constants
import modules.activities.activity.events as activity_events
import modules.activities.activity.integration_service as activity_integration
import modules.activities.activity.models as activity_models
import modules.activities.activity_file_storage.constants as file_storage_constants
import modules.activities.activity_file_storage.crud as file_storage_crud
import modules.activities.activity_file_storage.files as file_storage_files
import modules.activities.activity_file_storage.integration_service as file_storage
import modules.activities.activity_file_storage.models as file_models
import modules.activities.activity_file_storage.service as file_storage_service
import modules.activities.activity_file_storage.subscribers as file_subscribers
import modules.activities.activity_ingestion.contracts as ingestion_contracts
import modules.activities.activity_ingestion.migration_service as migration_service
import modules.activities.activity_ingestion.pipeline_service as pipeline_service
import modules.activities.activity_ingestion.recompute_service as recompute_service
import modules.activities.activity_ingestion.reprocess_service as reprocess_service
import modules.activities.activity_streams.constants as stream_constants
import modules.activities.activity_streams.contracts as stream_contracts
import modules.activities.activity_streams.crud as streams_crud
import modules.activities.activity_streams.models as stream_models
import modules.activities.activity_streams.samples as stream_samples
import modules.activities.activity_streams.service as streams_service
from tests._factories.activities import DEFAULT_START, make_activity
from tests._factories.ingestion import ConnectionProbe, retain_file, retained_file, store_legacy_file
from tests._factories.reprocess import (
    FIXTURES,
    OLD,
    RUN,
    TRIATHLON,
    import_fixture,
    import_legacy_legs,
    start_ordered,
    store_as_legacy_files,
)
from tests._factories.users import make_user
from tests._helpers.concurrency import Worker, wait_until_a_session_waits_for_a_lock

_AREA = file_storage_constants.ACTIVITY_FILE_STORAGE_AREA
_State = file_storage_constants.ActivityFileState
_Outcome = migration_service.ReprocessOutcome
_TCX = FIXTURES / "outdoor_run" / "activity_24273515840.tcx"
_RUN_BYTES = RUN.read_bytes()


@pytest.fixture
def owner(db: Session):
    """A user whose timezone and units the reprocess reads."""
    user = make_user(db, timezone="Europe/Lisbon")
    db.commit()
    return user


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _row(db: Session, activity_id: uuid.UUID) -> activity_models.Activity:
    db.expire_all()
    return db.execute(select(activity_models.Activity).where(activity_models.Activity.id == activity_id)).scalar_one()


def _files(db: Session) -> list[file_models.ActivityFile]:
    db.expire_all()
    return list(db.scalars(select(file_models.ActivityFile).order_by(file_models.ActivityFile.created_at)).all())


def _precedences(db: Session, activity_id: uuid.UUID) -> list[int]:
    db.expire_all()
    return sorted(
        db.scalars(
            select(activity_models.ActivitySource.precedence).where(
                activity_models.ActivitySource.activity_id == activity_id,
                activity_models.ActivitySource.kind == "file",
            )
        )
    )


def _keys(storage, prefix: str) -> list[str]:
    return sorted(storage.list_keys(_AREA, prefix))


def _legacy(db: Session, user_id: uuid.UUID, source: Path, tmp_path: Path, storage) -> uuid.UUID:
    """Import a file, then leave it the way v0.21 stored it: a copy under ``processed/``, no row, a source at 2."""
    [activity_id] = import_fixture(db, user_id, source, tmp_path, storage)
    store_as_legacy_files(db, [activity_id], storage)
    db.execute(
        update(activity_models.ActivitySource)
        .where(activity_models.ActivitySource.activity_id == activity_id)
        .values(precedence=2)
    )
    db.commit()
    return activity_id


def _plain_legacy(db: Session, user_id: uuid.UUID, data: bytes, storage, *, day: int = 1, **overrides) -> uuid.UUID:
    """Store an activity whose file is a legacy copy of ``data`` and that no session of the file starts."""
    activity = make_activity(db, user_id, start_time=DEFAULT_START.replace(day=day), **overrides)
    db.commit()
    store_legacy_file(activity.id, data, storage)
    return activity.id


class TestAdoptingALegacyFile:
    def test_a_legacy_fit_becomes_a_row_at_the_key_it_has_and_is_reprocessed_from_it(
        self, db, owner, storage, tmp_path
    ):
        activity_id = _legacy(db, owner.id, RUN, tmp_path, storage)

        outcome = migration_service.reprocess_activity(activity_id, storage)

        assert outcome is _Outcome.REPROCESSED
        [file] = _files(db)
        row = _row(db, activity_id)
        assert row.file_id == file.id
        assert (file.user_id, file.sha256, file.extension, file.size_bytes, file.state) == (
            owner.id,
            _sha(_RUN_BYTES),
            ".fit",
            len(_RUN_BYTES),
            _State.ATTACHED,
        )
        assert file.storage_key == f"processed/{activity_id}.fit"
        assert _keys(storage, "files/") == []
        assert storage.get(_AREA, file.storage_key) == _RUN_BYTES
        assert row.analysis_version == 1

    def test_a_fit_source_keeps_the_device_file_precedence(self, db, owner, storage, tmp_path):
        activity_id = _legacy(db, owner.id, RUN, tmp_path, storage)

        migration_service.reprocess_activity(activity_id, storage)

        assert _precedences(db, activity_id) == [2]

    def test_a_tcx_source_takes_the_generic_file_precedence(self, db, owner, storage, tmp_path):
        activity_id = _legacy(db, owner.id, _TCX, tmp_path, storage)
        assert _precedences(db, activity_id) == [2]

        migration_service.reprocess_activity(activity_id, storage)

        assert _precedences(db, activity_id) == [1]
        [file] = _files(db)
        assert file.extension == ".tcx"

    def test_a_file_that_cannot_be_parsed_is_adopted_all_the_same(self, db, owner, storage):
        activity_id = _plain_legacy(db, owner.id, b"this is not a fit file at all", storage)

        outcome = migration_service.reprocess_activity(activity_id, storage)

        assert outcome is _Outcome.FAILED
        [file] = _files(db)
        assert _row(db, activity_id).file_id == file.id
        assert file.sha256 == _sha(b"this is not a fit file at all")

    def test_a_file_with_no_session_for_the_activity_is_adopted_all_the_same(self, db, owner, storage):
        activity_id = _plain_legacy(db, owner.id, _RUN_BYTES, storage)

        outcome = migration_service.reprocess_activity(activity_id, storage)

        assert outcome is _Outcome.NO_SESSION
        [file] = _files(db)
        assert _row(db, activity_id).file_id == file.id

    def test_an_activity_with_no_source_takes_the_files(self, db, owner, storage):
        activity_id = _plain_legacy(db, owner.id, _RUN_BYTES, storage)
        assert _precedences(db, activity_id) == []

        migration_service.reprocess_activity(activity_id, storage)

        db.expire_all()
        source = db.scalars(
            select(activity_models.ActivitySource).where(activity_models.ActivitySource.activity_id == activity_id)
        ).one()
        assert (source.kind, source.file_sha256, source.precedence) == ("file", _sha(_RUN_BYTES), 2)

    def test_a_leg_never_takes_a_file(self, db, owner, storage):
        parent = make_activity(db, owner.id)
        leg = make_activity(db, owner.id, parent_activity_id=parent.id, start_time=DEFAULT_START.replace(day=2))
        db.commit()
        store_legacy_file(leg.id, _RUN_BYTES, storage)

        migration_service.reprocess_activity(leg.id, storage)

        assert _row(db, leg.id).file_id is None
        assert _files(db) == []

    def test_a_second_visit_adopts_nothing_again(self, db, owner, storage, tmp_path):
        activity_id = _legacy(db, owner.id, RUN, tmp_path, storage)
        migration_service.reprocess_activity(activity_id, storage)
        before = [(file.id, file.updated_at) for file in _files(db)]

        assert migration_service.reprocess_activity(activity_id, storage) is _Outcome.REPROCESSED

        assert [(file.id, file.updated_at) for file in _files(db)] == before
        assert _keys(storage, "processed/") == [f"processed/{activity_id}.fit"]

    def test_an_activity_deleted_meanwhile_leaves_no_row(self, committed_sessions, storage, monkeypatch):
        with committed_sessions() as db:
            user = make_user(db)
            db.commit()
            activity_id = _plain_legacy(db, user.id, _RUN_BYTES, storage)
        real = file_storage.stage_adoption

        def deleted_first(*args, **kwargs):
            with committed_sessions() as other:
                other.execute(delete(activity_models.Activity).where(activity_models.Activity.id == activity_id))
                other.commit()
            return real(*args, **kwargs)

        monkeypatch.setattr(file_storage, "stage_adoption", deleted_first)

        assert migration_service.reprocess_activity(activity_id, storage) is _Outcome.NO_FILE

        with committed_sessions() as db:
            assert _files(db) == []

    def test_an_activity_that_took_a_file_row_meanwhile_keeps_that_one(self, committed_sessions, storage, monkeypatch):
        with committed_sessions() as db:
            user = make_user(db)
            db.commit()
            activity_id = _plain_legacy(db, user.id, _RUN_BYTES, storage)
        real = file_storage.stage_adoption
        taken: list[uuid.UUID] = []

        def recomputed_first(*args, **kwargs):
            taken.append(retain_file(user.id, activity_id, b"a better source", storage))
            return real(*args, **kwargs)

        monkeypatch.setattr(file_storage, "stage_adoption", recomputed_first)

        assert migration_service.reprocess_activity(activity_id, storage) is _Outcome.NO_FILE

        with committed_sessions() as db:
            assert [file.id for file in _files(db)] == taken
            assert _row(db, activity_id).file_id == taken[0]


class TestSameBytesCollapse:
    def test_activities_of_the_same_bytes_share_the_row_of_the_first_and_the_extra_blobs_go(self, db, owner, storage):
        activities = [_plain_legacy(db, owner.id, _RUN_BYTES, storage, day=day) for day in (1, 2, 3)]

        for activity_id in activities:
            migration_service.reprocess_activity(activity_id, storage)

        [file] = _files(db)
        assert file.storage_key == f"processed/{activities[0]}.fit"
        assert {_row(db, activity_id).file_id for activity_id in activities} == {file.id}
        assert _keys(storage, "processed/") == [file.storage_key]
        assert all(retained_file(activity_id, storage) == (".fit", _RUN_BYTES) for activity_id in activities)

    def test_another_users_identical_bytes_get_a_row_of_their_own(self, db, owner, storage):
        other = make_user(db)
        db.commit()
        mine = _plain_legacy(db, owner.id, _RUN_BYTES, storage)
        theirs = _plain_legacy(db, other.id, _RUN_BYTES, storage)

        migration_service.reprocess_activity(mine, storage)
        migration_service.reprocess_activity(theirs, storage)

        assert len(_files(db)) == 2
        assert len(_keys(storage, "processed/")) == 2

    def test_a_shared_row_whose_blob_is_gone_is_written_again_from_the_adopted_bytes(self, db, owner, storage):
        first = _plain_legacy(db, owner.id, _RUN_BYTES, storage, day=1)
        second = _plain_legacy(db, owner.id, _RUN_BYTES, storage, day=2)
        migration_service.reprocess_activity(first, storage)
        storage.delete(_AREA, f"processed/{first}.fit")

        migration_service.reprocess_activity(second, storage)

        [file] = _files(db)
        assert storage.get(_AREA, file.storage_key) == _RUN_BYTES
        assert _keys(storage, "processed/") == [f"processed/{first}.fit"]

    def test_a_pending_row_of_an_upload_in_flight_is_taken_and_given_its_blob(self, db, owner, storage):
        activity_id = _plain_legacy(db, owner.id, _RUN_BYTES, storage)
        with core_database.SessionLocal() as session:
            pending, _state, _created = file_storage_crud.take_live_file(
                owner.id, _sha(_RUN_BYTES), ".fit", len(_RUN_BYTES), session
            )
            session.commit()
        assert storage.get(_AREA, pending.storage_key) is None

        migration_service.reprocess_activity(activity_id, storage)

        [file] = _files(db)
        assert (file.id, file.state) == (pending.file_id, _State.ATTACHED)
        assert _row(db, activity_id).file_id == pending.file_id
        assert storage.get(_AREA, pending.storage_key) == _RUN_BYTES
        assert _keys(storage, "processed/") == []

    def test_deleting_the_activity_whose_key_the_row_carries_keeps_the_file_for_the_others(self, db, owner, storage):
        first = _plain_legacy(db, owner.id, _RUN_BYTES, storage, day=1)
        second = _plain_legacy(db, owner.id, _RUN_BYTES, storage, day=2)
        migration_service.reprocess_activity(first, storage)
        migration_service.reprocess_activity(second, storage)
        [file] = _files(db)
        db.execute(delete(activity_models.Activity).where(activity_models.Activity.id == first))
        db.commit()

        file_storage_service.release_unreferenced(file.id, storage)

        assert storage.get(_AREA, file.storage_key) == _RUN_BYTES
        assert [row.id for row in _files(db)] == [file.id]


class TestTheOrderOfTheSteps:
    def test_the_legs_of_a_multi_session_file_are_regrouped_and_the_file_is_kept_once_under_the_parent(
        self, db, owner, storage, tmp_path, monkeypatch
    ):
        legs = start_ordered(db, import_legacy_legs(db, owner.id, TRIATHLON, tmp_path, storage, monkeypatch))
        db.execute(
            update(activity_models.ActivitySource)
            .where(activity_models.ActivitySource.activity_id.in_(legs))
            .values(precedence=1)
        )
        db.commit()

        migration_service.reprocess_activity(legs[2], storage)

        parent_id = _row(db, legs[0]).parent_activity_id
        assert parent_id is not None
        [file] = _files(db)
        assert _row(db, parent_id).file_id == file.id
        assert [_row(db, leg).file_id for leg in legs] == [None] * len(legs)
        assert _keys(storage, "processed/") == []
        assert _precedences(db, legs[0]) == [2], "a leg's source takes the precedence of its parent's file"
        parent = _row(db, parent_id)
        assert (parent.start_latitude, parent.start_longitude) != (None, None)

    def test_the_regroup_is_tried_before_the_adoption_and_the_adoption_before_the_plan(
        self, db, owner, other_user, storage, tmp_path, monkeypatch
    ):
        legacy = import_legacy_legs(db, owner.id, TRIATHLON, tmp_path, storage, monkeypatch)
        ordered = start_ordered(db, legacy)
        missing = ordered.pop()
        file_storage.delete_legacy_activity_file(missing, storage)
        db.execute(delete(activity_models.Activity).where(activity_models.Activity.id == missing))
        db.commit()
        calls: list[str] = []

        def recording(owner_module, name: str, label: str) -> None:
            real = getattr(owner_module, name)

            def call(*args, **kwargs):
                calls.append(label)
                return real(*args, **kwargs)

            monkeypatch.setattr(owner_module, name, call)

        recording(reprocess_service, "_regroup", "regroup")
        recording(file_storage, "stage_adoption", "adopt")
        recording(recompute_service, "plan", "plan")

        migration_service.reprocess_activity(ordered[0], storage)

        assert calls == ["regroup", "adopt", "plan"]

    def test_the_write_expects_the_adopted_row(self, db, owner, storage, tmp_path, monkeypatch):
        activity_id = _legacy(db, owner.id, RUN, tmp_path, storage)
        planned: list[object] = []
        real = recompute_service.plan

        def recording(pairs, parsed_file, expected_file_ids=None):
            planned.append(expected_file_ids)
            return real(pairs, parsed_file, expected_file_ids)

        monkeypatch.setattr(recompute_service, "plan", recording)

        assert migration_service.reprocess_activity(activity_id, storage) is _Outcome.REPROCESSED

        [file] = _files(db)
        assert planned == [{activity_id: file.id}]

    def test_the_adoption_takes_the_matching_lock_before_it_changes_anything(
        self, db, owner, storage, tmp_path, monkeypatch
    ):
        activity_id = _legacy(db, owner.id, RUN, tmp_path, storage)
        calls: list[str] = []
        for module, name, label in (
            (activity_integration, "lock_user_matching", "lock"),
            (file_storage, "stage_adoption", "stage"),
            (activity_integration, "set_file_id", "set_file_id"),
        ):
            real = getattr(module, name)

            def call(*args, _real=real, _label=label, **kwargs):
                calls.append(_label)
                return _real(*args, **kwargs)

            monkeypatch.setattr(module, name, call)

        migration_service.reprocess_activity(activity_id, storage)

        assert calls == ["lock", "stage", "set_file_id"]

    def test_an_import_that_is_matching_holds_the_adoption_until_it_commits(
        self, committed_sessions, owner_committed, storage, tmp_path
    ):
        user_id, activity_id = owner_committed
        with committed_sessions() as importing:
            activity_integration.lock_user_matching(user_id, importing)
            worker = Worker(lambda: migration_service.reprocess_activity(activity_id, storage))
            wait_until_a_session_waits_for_a_lock(committed_sessions)
            assert not worker.done
            importing.rollback()
        worker.join()

        assert worker.error is None
        with committed_sessions() as db:
            assert _row(db, activity_id).file_id is not None

    def test_no_database_session_is_open_across_a_storage_call(self, committed_sessions, owner_committed, storage):
        user_id, activity_id = owner_committed
        with committed_sessions() as db:
            twin = _plain_legacy(db, user_id, _RUN_BYTES, storage, day=5)
        probe = ConnectionProbe(storage, ("get", "save", "delete", "stat"))

        migration_service.reprocess_activity(activity_id, probe)
        migration_service.reprocess_activity(twin, probe)

        assert len(probe.open_during_calls) >= 4
        assert set(probe.open_during_calls) == {0}


@pytest.fixture
def other_user(db: Session):
    user = make_user(db)
    db.commit()
    return user


@pytest.fixture
def owner_committed(committed_sessions, storage, tmp_path):
    """A user and a legacy FIT activity of theirs, committed on real connections."""
    with committed_sessions() as db:
        user = make_user(db, timezone="Europe/Lisbon")
        db.commit()
        activity_id = _legacy(db, user.id, RUN, tmp_path, storage)
    return user.id, activity_id


def _old_streams(db: Session, activity_id: uuid.UUID, *, numeric_time: bool = False) -> None:
    """Give an activity the waypoint streams v0.21 stored: a track and a heart rate."""

    def stamp(second: int) -> object:
        return second if numeric_time else (DEFAULT_START + timedelta(seconds=second)).strftime("%Y-%m-%dT%H:%M:%S")

    db.add_all(
        [
            stream_models.ActivityStreams(
                activity_id=activity_id,
                stream_type=stream_constants.STREAM_TYPE_MAP,
                stream_waypoints=[
                    {"time": stamp(second), "lat": 38.7 + second / 1000, "lon": -9.1} for second in range(3)
                ],
            ),
            stream_models.ActivityStreams(
                activity_id=activity_id,
                stream_type=stream_constants.STREAM_TYPE_HR,
                stream_waypoints=[{"time": stamp(second), "hr": 100 + second} for second in range(3)],
            ),
        ]
    )
    db.commit()


def _samples(db: Session, activity_id: uuid.UUID):
    db.expire_all()
    return streams_crud.get_activity_samples(activity_id, db)


def _old_stream_count(db: Session, activity_id: uuid.UUID) -> int:
    db.expire_all()
    return len(streams_crud.get_activity_streams(activity_id, db))


class TestConvertingOldStreams:
    def test_a_strava_activity_with_only_old_streams_takes_samples_and_a_start_point(self, db, owner, storage):
        activity = make_activity(db, owner.id, strava_activity_id=1234)
        db.commit()
        _old_streams(db, activity.id, numeric_time=True)
        assert _row(db, activity.id).start_latitude is None

        assert migration_service.reprocess_activity(activity.id, storage) is _Outcome.NO_FILE
        assert migration_service.convert_legacy_streams(activity.id) is True

        samples = _samples(db, activity.id)
        assert samples is not None
        assert samples.offsets_ms == [0, 1000, 2000]
        assert samples.heart_rate == [100, 101, 102]
        assert _old_stream_count(db, activity.id) == 0
        row = _row(db, activity.id)
        assert (row.start_latitude, row.start_longitude) == (38.7, -9.1)

    def test_the_conversion_is_what_the_read_time_fallback_serves(self, db, owner):
        activity = make_activity(db, owner.id)
        db.commit()
        _old_streams(db, activity.id)
        expected = stream_samples.samples_from_streams(
            streams_crud.get_activity_streams(activity.id, db), activity.start_time
        )

        migration_service.convert_legacy_streams(activity.id)

        assert _samples(db, activity.id) == expected

    def test_a_provider_start_point_is_kept(self, db, owner):
        activity = make_activity(db, owner.id, start_latitude=1.0, start_longitude=2.0)
        db.commit()
        _old_streams(db, activity.id)

        migration_service.convert_legacy_streams(activity.id)

        row = _row(db, activity.id)
        assert (row.start_latitude, row.start_longitude) == (1.0, 2.0)

    def test_the_conversion_leaves_version_and_updated_at_alone(self, db, owner):
        activity = make_activity(db, owner.id)
        db.commit()
        _old_streams(db, activity.id)
        before = _row(db, activity.id)
        version, updated_at = before.version, before.updated_at

        migration_service.convert_legacy_streams(activity.id)

        after = _row(db, activity.id)
        assert (after.version, after.updated_at) == (version, updated_at)

    def test_an_activity_that_already_has_samples_only_loses_its_old_streams(self, db, owner):
        activity = make_activity(db, owner.id)
        db.commit()
        streams_crud.create_activity_samples(
            activity.id, stream_contracts.ParsedSamples(offsets_ms=[0], heart_rate=[77.0]), db
        )
        db.commit()
        _old_streams(db, activity.id)

        migration_service.convert_legacy_streams(activity.id)

        samples = _samples(db, activity.id)
        assert samples is not None and samples.heart_rate == [77.0]
        assert _old_stream_count(db, activity.id) == 0

    def test_an_activity_with_no_old_streams_and_an_unknown_one_are_no_ops(self, db, owner):
        activity = make_activity(db, owner.id)
        db.commit()

        assert migration_service.convert_legacy_streams(activity.id) is False
        assert migration_service.convert_legacy_streams(uuid.uuid4()) is False

    def test_a_file_that_cannot_be_read_leaves_its_activity_with_samples_from_the_old_streams(self, db, owner, storage):
        activity_id = _plain_legacy(db, owner.id, b"this is not a fit file at all", storage)
        _old_streams(db, activity_id)

        outcome = migration_service.reprocess_activity(activity_id, storage)
        migration_service.convert_legacy_streams(activity_id)

        assert outcome is _Outcome.FAILED
        assert _samples(db, activity_id) is not None
        assert _old_stream_count(db, activity_id) == 0

    def test_a_reprocessed_activity_ends_with_no_old_streams_and_its_files_start_point(
        self, db, owner, storage, tmp_path
    ):
        activity_id = _legacy(db, owner.id, RUN, tmp_path, storage)
        _old_streams(db, activity_id)
        db.execute(
            update(activity_models.Activity)
            .where(activity_models.Activity.id == activity_id)
            .values(start_latitude=None, start_longitude=None, analysis_version=0)
        )
        db.commit()

        assert migration_service.reprocess_activity(activity_id, storage) is _Outcome.REPROCESSED

        assert _old_stream_count(db, activity_id) == 0
        row = _row(db, activity_id)
        assert row.start_latitude is not None
        samples = _samples(db, activity_id)
        assert samples is not None and samples.offsets_ms != [0, 1000, 2000]


class TestTheHashOfALegacyFileSource:
    def test_a_gzipped_upload_is_hashed_as_the_decompressed_bytes_it_retains(self, db, owner, storage, tmp_path):
        staged = tmp_path / "upload.fit.gz"
        staged.write_bytes(gzip.compress(_RUN_BYTES))

        [activity] = pipeline_service.validate_prepare_and_store_file(
            owner.id, str(staged), db, source=ingestion_contracts.UploadSource(), storage=storage
        )
        db.commit()

        source = db.scalars(
            select(activity_models.ActivitySource).where(activity_models.ActivitySource.activity_id == activity.id)
        ).one()
        [file] = _files(db)
        assert source.file_sha256 == file.sha256 == _sha(_RUN_BYTES)
        assert storage.get(_AREA, file.storage_key) == _RUN_BYTES


class TestTheWalkLeavesNoLegacyLayout:
    """Once the walk has run, the code that reads the layout of an earlier release has nothing to read."""

    def _corpus(self, db: Session, owner, storage, tmp_path, monkeypatch) -> list[uuid.UUID]:
        ids: list[uuid.UUID] = []
        ids.append(_legacy(db, owner.id, RUN, tmp_path, storage))
        ids.append(_legacy(db, owner.id, _TCX, tmp_path, storage))
        ids += import_legacy_legs(db, owner.id, TRIATHLON, tmp_path, storage, monkeypatch)
        ids += [_plain_legacy(db, owner.id, _RUN_BYTES, storage, day=day) for day in (11, 12)]
        garbage = _plain_legacy(db, owner.id, b"this is not a fit file at all", storage, day=13)
        _old_streams(db, garbage)
        strava = make_activity(db, owner.id, strava_activity_id=99, start_time=DEFAULT_START.replace(day=14))
        db.commit()
        _old_streams(db, strava.id, numeric_time=True)
        ids += [garbage, strava.id]
        no_file = make_activity(db, owner.id, start_time=DEFAULT_START.replace(day=15))
        db.commit()
        _old_streams(db, no_file.id)
        ids.append(no_file.id)
        restored = import_fixture(db, owner.id, RUN, tmp_path, storage)  # already a row, at version 0 below
        ids += restored
        db.execute(
            update(activity_models.Activity)
            .where(activity_models.Activity.id.in_(ids))
            .values(analysis_version=0, updated_at=OLD)
        )
        db.commit()
        return ids

    def test_no_activity_needs_the_legacy_read_paths_after_the_walk(
        self, db, owner, storage, platform, tmp_path, monkeypatch
    ):
        ids = self._corpus(db, owner, storage, tmp_path, monkeypatch)

        assert reprocess_job.run_batch(storage, None) is False

        # Storage: every activity that had a retained file references a row, and every blob under processed/ is named.
        db.expire_all()
        stream_rows = db.scalars(select(stream_models.ActivityStreams.id)).all()
        assert stream_rows == [], "the old streams table is empty"
        rows = _files(db)
        named = {file.storage_key for file in rows}
        assert set(_keys(storage, "processed/")) <= named
        assert not set(file_storage_service.live_processed_keys(_keys(storage, "processed/"), db)) - named
        for activity_id in ids:
            activity = _row(db, activity_id)
            has_blob = any(storage.get(_AREA, key) for key in _legacy_keys(activity_id))
            assert not has_blob or activity.file_id is not None
            if activity.file_id is not None and activity.parent_activity_id is None:
                ref = file_storage.resolve_refs([activity.file_id], db)[activity.file_id]
                assert storage.get(_AREA, ref.storage_key) is not None
                assert _precedences_match(db, activity_id, ref)
        # Samples: every activity that had streams has samples and a start point when they hold a position.
        for activity_id in ids:
            samples = _samples(db, activity_id)
            if samples is not None and samples.latitude is not None:
                assert _row(db, activity_id).start_latitude is not None

        # The legacy readers find nothing to read.
        def only_nothing(owner_module, name: str, check) -> None:
            real = getattr(owner_module, name)

            def call(*args, **kwargs):
                result = real(*args, **kwargs)
                check(args, result)
                return result

            monkeypatch.setattr(owner_module, name, call)

        only_nothing(
            file_storage_files, "read_legacy_file", lambda _args, result: _expect(result is None, "legacy read")
        )
        only_nothing(streams_crud, "get_activity_streams", lambda _args, result: _expect(result == [], "streams read"))

        def deleted_nothing(args, _result) -> None:
            _expect(not any(storage.get(_AREA, key) for key in _legacy_keys(args[0])), "legacy delete")

        real_delete = file_storage_files.delete_legacy_files

        def checked_delete(activity_id, provider):
            deleted_nothing((activity_id,), None)
            return real_delete(activity_id, provider)

        monkeypatch.setattr(file_storage_files, "delete_legacy_files", checked_delete)

        for activity_id in ids:
            migration_service.reprocess_activity(activity_id, storage)
            owner_of = _row(db, activity_id).user_id
            streams_service.get_activity_streams(activity_id, owner_of, db)
            file_id = _row(db, activity_id).file_id
            file_subscribers.cleanup_activity_file_for_event(
                _deleted(activity_id, None if file_id is None else file_id)
            )
        # The activities still exist, so no cleanup removed a file they reference.
        assert all(storage.get(_AREA, file.storage_key) is not None for file in _files(db))


def _expect(condition: bool, what: str) -> None:
    assert condition, f"a legacy path found something to {what}"


def _legacy_keys(activity_id: uuid.UUID) -> list[str]:
    return [
        file_storage_files.legacy_file_key(activity_id, extension) for extension in file_storage_files.STORED_EXTENSIONS
    ]


def _precedences_match(db: Session, activity_id: uuid.UUID, ref) -> bool:
    db.expire_all()
    return all(
        precedence == activity_constants.file_source_precedence(ref.extension)
        for precedence in db.scalars(
            select(activity_models.ActivitySource.precedence).where(
                activity_models.ActivitySource.activity_id == activity_id,
                activity_models.ActivitySource.file_sha256 == ref.sha256,
            )
        )
    )


def _deleted(activity_id: uuid.UUID, file_id: uuid.UUID | None) -> platform_events.Event:
    payload = {"activity_id": str(activity_id)}
    if file_id is not None:
        payload["file_id"] = str(file_id)
    return platform_events.Event(
        event_id=str(uuid.uuid4()),
        event_type=activity_events.ACTIVITY_DELETED,
        source="test",
        timestamp="2026-01-01T00:00:00+00:00",
        payload=payload,
        retry_count=1,
        max_attempts=3,
    )
