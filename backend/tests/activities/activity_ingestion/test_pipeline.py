"""The ingestion pipeline's behaviour on real files: parse, enrich, store, retain, and what a refusal leaves behind."""

import gzip
import logging
import os
import tempfile
import uuid

import pytest
from jasil.providers import StorageBackendUnavailableError
from sqlalchemy import select, text

import core.config as core_config
import modules.activities.activity_exercise_titles.models as exercise_title_models
import modules.activities.activity_file_storage.integration_service as file_storage
import modules.activities.activity_ingestion.integration_service as ingestion_integration
import modules.activities.activity_laps.models as lap_models
import modules.activities.contributor_registry as activities_contributor_registry
from tests._factories.garmin import EMPTY_GPX, activity_gpx, zip_of
from tests._factories.ingestion import activities_of, fit_file, long_gpx, read_job

_API = core_config.ROOT_PATH


@pytest.fixture
def me(make_signed_in):
    """A signed-in regular user."""
    return make_signed_in()


@pytest.fixture
def scratch(tmp_path, monkeypatch):
    """The directory the pipeline's temporary files go to, so what it leaves behind can be listed."""
    directory = tmp_path / "scratch"
    directory.mkdir()
    monkeypatch.setattr(tempfile, "tempdir", str(directory))
    return directory


def _upload(user, name: str, content: bytes):
    return user.client.post(f"{_API}/activities/upload", files={"file": (name, content)})


class TestAFileWithSeveralActivities:
    def test_stores_each_activity_with_its_own_copy_of_the_source_file(self, me, pool, committed_sessions, storage):
        content = fit_file(activities=2)

        response = _upload(me, "double.fit", content)
        pool.drain()

        activities = activities_of(committed_sessions, me.user.id)
        state = me.client.get(f"{_API}/jobs/{response.json()['id']}").json()
        assert len(activities) == 2
        assert sorted(state["activity_ids"]) == sorted(str(activity.id) for activity in activities)
        for activity in activities:
            assert file_storage.get_activity_file(activity.id, storage) == (f"{activity.id}.fit", content)

    def test_uploaded_again_it_adds_nothing(self, me, pool, committed_sessions):
        _upload(me, "double.fit", fit_file(activities=2))
        pool.drain()
        _upload(me, "again.fit", fit_file(activities=2))
        pool.drain()

        assert len(activities_of(committed_sessions, me.user.id)) == 2


class TestAFileWithRecordsButNoSession:
    def test_leaves_no_retained_file_and_no_temporary_file(self, me, pool, committed_sessions, storage, scratch):
        response = _upload(me, "nosession.fit", fit_file(with_session=False))
        pool.drain()

        assert read_job(committed_sessions, uuid.UUID(response.json()["id"])).error_code == "invalid_file"
        assert activities_of(committed_sessions, me.user.id) == []
        assert list(storage.list_keys("activity_files", "processed/")) == []
        assert os.listdir(scratch) == []


class TestAFileTheParserCannotRead:
    def test_is_the_files_fault_an_invalid_file_and_no_error_of_the_servers(
        self, me, pool, committed_sessions, caplog, scratch
    ):
        broken = activity_gpx().replace(b"<time>", b"<note>").replace(b"</time>", b"</note>")

        with caplog.at_level(logging.DEBUG):
            response = _upload(me, "broken.gpx", broken)
            pool.drain()

        row = read_job(committed_sessions, uuid.UUID(response.json()["id"]))
        assert (row.status, row.error_code) == ("failed", "invalid_file")
        assert [record for record in caplog.records if record.levelno >= logging.ERROR] == []
        assert os.listdir(scratch) == []


class TestFileScopedData:
    def test_a_fit_files_exercise_titles_are_stored_through_their_contributor(self, me, pool, committed_sessions):
        content = fit_file(exercise_titles=(("Bench press", 0, 1),))

        _upload(me, "titles.fit", content)
        pool.drain()

        with committed_sessions() as db:
            titles = db.scalars(select(exercise_title_models.ActivityExerciseTitles)).all()
        assert [(title.exercise_category, title.exercise_name, title.wkt_step_name) for title in titles] == [
            (0, 1, "Bench press")
        ]
        assert len(activities_of(committed_sessions, me.user.id)) == 1

    def test_a_component_nobody_registered_for_fails_the_import_instead_of_dropping_it(
        self, me, pool, committed_sessions, monkeypatch
    ):
        monkeypatch.setattr(activities_contributor_registry, "_file_ingestion", {})

        response = _upload(me, "titles.fit", fit_file(exercise_titles=(("Bench press", 0, 1),)))
        pool.drain()

        state = me.client.get(f"{_API}/jobs/{response.json()['id']}").json()
        assert (state["status"], state["error_code"]) == ("failed", "processing_failed")
        assert "exercise_titles" not in str(state)
        assert activities_of(committed_sessions, me.user.id) == []


class TestTheOwnersContext:
    def test_the_owners_timezone_applies_to_a_file_with_no_position(self, make_signed_in, committed_sessions, pool):
        tokyo = make_signed_in(timezone="Asia/Tokyo")

        _upload(tokyo, "treadmill.fit", fit_file(with_gps=False))
        pool.drain()

        (activity,) = activities_of(committed_sessions, tokyo.user.id)
        assert activity.timezone == "Asia/Tokyo"

    def test_the_server_timezone_applies_when_the_owner_has_none(self, make_signed_in, committed_sessions, pool):
        plain = make_signed_in(timezone=None)

        _upload(plain, "treadmill.fit", fit_file(with_gps=False))
        pool.drain()

        (activity,) = activities_of(committed_sessions, plain.user.id)
        assert activity.timezone == core_config.settings.TZ

    @pytest.mark.parametrize(("units", "lap_metres"), [("metric", (1000, 1100)), ("imperial", (1600, 1700))])
    def test_the_owners_units_set_the_length_of_an_automatic_lap(
        self, make_signed_in, committed_sessions, pool, units, lap_metres
    ):
        owner = make_signed_in(units=units)

        _upload(owner, "long.gpx", long_gpx(kilometres=5.2))
        pool.drain()

        (activity,) = activities_of(committed_sessions, owner.user.id)
        with committed_sessions() as db:
            first = db.scalars(
                select(lap_models.ActivityLaps)
                .where(lap_models.ActivityLaps.activity_id == activity.id)
                .order_by(lap_models.ActivityLaps.start_time)
            ).first()
        assert first is not None
        assert lap_metres[0] <= first.total_distance <= lap_metres[1]


class TestAGzippedFile:
    """A ``.gz`` member of a bulk import: the archive is decompressed to a temporary copy that never outlives it."""

    def _import(self, me, members: dict[str, bytes]):
        return me.client.post(f"{_API}/activities/bulk-import", files={"file": ("export.zip", zip_of(members))})

    def test_is_decompressed_imported_and_leaves_no_temporary_copy(
        self, me, pool, committed_sessions, scratch, storage
    ):
        response = self._import(me, {"ride.gpx.gz": gzip.compress(activity_gpx())})
        pool.drain()

        row = read_job(committed_sessions, uuid.UUID(response.json()["id"]))
        (activity,) = activities_of(committed_sessions, me.user.id)
        assert (row.files_done, row.files_failed) == (1, 0)
        assert file_storage.get_activity_file(activity.id, storage) == (f"{activity.id}.gpx", activity_gpx())
        assert os.listdir(scratch) == []

    def test_one_that_decompresses_to_an_unsupported_payload_fails_and_leaves_no_temporary_copy(
        self, me, pool, committed_sessions, scratch
    ):
        response = self._import(me, {"notes.txt.gz": gzip.compress(b"hello"), "ok.gpx": activity_gpx()})
        pool.drain()

        row = read_job(committed_sessions, uuid.UUID(response.json()["id"]))
        assert (row.files_done, row.files_failed) == (1, 1)
        assert os.listdir(scratch) == []

    def test_one_whose_content_the_parser_refuses_fails_without_touching_the_rest(
        self, me, pool, committed_sessions, scratch
    ):
        response = self._import(me, {"empty.gpx.gz": gzip.compress(EMPTY_GPX), "ok.gpx": activity_gpx()})
        pool.drain()

        row = read_job(committed_sessions, uuid.UUID(response.json()["id"]))
        assert (row.files_done, row.files_failed) == (1, 1)
        assert os.listdir(scratch) == []


class TestAProviderFile:
    def test_a_file_the_pipeline_refuses_is_skipped_and_the_session_stays_usable(
        self, me, committed_sessions, tmp_path
    ):
        refused = tmp_path / "empty.gpx"
        refused.write_bytes(EMPTY_GPX)
        good = tmp_path / "good.gpx"
        good.write_bytes(activity_gpx())
        source = ingestion_integration.UploadSource()

        with committed_sessions() as db:
            assert ingestion_integration.ingest_activity_file(me.user.id, str(refused), db, source=source) is None
            stored = ingestion_integration.ingest_activity_file(me.user.id, str(good), db, source=source)

        assert stored is not None and len(stored) == 1

    def test_an_outage_is_raised_so_the_window_retries(self, me, committed_sessions, tmp_path, break_storage):
        good = tmp_path / "good.gpx"
        good.write_bytes(activity_gpx())
        break_storage(save=StorageBackendUnavailableError("storage is down"))

        with committed_sessions() as db, pytest.raises(StorageBackendUnavailableError):
            ingestion_integration.ingest_activity_file(
                me.user.id, str(good), db, source=ingestion_integration.UploadSource()
            )

    def test_a_file_with_an_unsupported_extension_is_refused_and_the_session_stays_usable(
        self, me, committed_sessions, tmp_path
    ):
        refused = tmp_path / "notes.txt"
        refused.write_bytes(b"hello")

        with committed_sessions() as db:
            assert (
                ingestion_integration.ingest_activity_file(
                    me.user.id, str(refused), db, source=ingestion_integration.UploadSource()
                )
                is None
            )

    def test_an_owner_without_privacy_settings_is_refused_rather_than_imported_with_guessed_defaults(
        self, me, committed_sessions, tmp_path
    ):
        good = tmp_path / "good.gpx"
        good.write_bytes(activity_gpx())
        with committed_sessions() as db:
            db.execute(text("DELETE FROM users_privacy_settings WHERE user_id = :id"), {"id": me.user.id})
            db.commit()

        with committed_sessions() as db:
            assert (
                ingestion_integration.ingest_activity_file(
                    me.user.id, str(good), db, source=ingestion_integration.UploadSource()
                )
                is None
            )
        assert activities_of(committed_sessions, me.user.id) == []

    def test_a_file_for_an_owner_that_does_not_exist_is_refused(self, committed_sessions, tmp_path):
        good = tmp_path / "good.gpx"
        good.write_bytes(activity_gpx())

        with committed_sessions() as db:
            assert (
                ingestion_integration.ingest_activity_file(
                    uuid.uuid4(), str(good), db, source=ingestion_integration.UploadSource()
                )
                is None
            )
