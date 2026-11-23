"""An uploaded activity file becomes the owner's activity, through the real route, pool, storage and database.

A client posts a real GPX, TCX or FIT; the route stages it in the platform storage and answers 202; the job runs on the
in-process pool the local profile has; the outcome is read back over ``GET /jobs/{id}``, in the activity rows and in
what storage still holds.
"""

import gzip
import os
import tempfile
import threading
import uuid

import pytest
from jasil.providers import StorageBackendUnavailableError

import core.config as core_config
import core.exceptions as core_exceptions
import core.local_pool as core_local_pool
import modules.activities.activity_file_storage.integration_service as file_storage
import modules.activities.activity_ingestion.background as ingestion_background
import modules.activities.activity_ingestion.constants as ingestion_constants
import modules.activities.activity_ingestion.service as ingestion_service
from tests._factories.garmin import EMPTY_GPX, activity_gpx
from tests._factories.ingestion import (
    activities_of,
    activity_tcx,
    all_jobs,
    fit_file,
    read_job,
    staged_keys,
)

_API = core_config.ROOT_PATH
_JOBS = f"{_API}/jobs"
_ErrorCode = ingestion_constants.IngestionJobErrorCode


@pytest.fixture
def me(make_signed_in):
    """A signed-in regular user."""
    return make_signed_in()


def _upload(user, name: str, content: bytes, **headers):
    return user.client.post(f"{_API}/activities/upload", files={"file": (name, content)}, headers=headers)


def _incoming_files() -> list[str]:
    directory = core_config.FILES_UPLOAD_INCOMING_DIR
    return os.listdir(directory) if os.path.isdir(directory) else []


def _job_state(user, job_id: str) -> dict:
    response = user.client.get(f"{_JOBS}/{job_id}")
    assert response.status_code == 200, response.text
    return response.json()


class TestAnImportedFile:
    @pytest.mark.parametrize(
        ("name", "content"),
        [
            pytest.param("ride.gpx", activity_gpx(), id="gpx"),
            pytest.param("ride.tcx", activity_tcx(), id="tcx"),
            pytest.param("ride.fit", fit_file(), id="fit"),
        ],
    )
    def test_becomes_the_owners_activity_and_its_source_file_is_retained(
        self, me, pool, committed_sessions, storage, name, content
    ):
        response = _upload(me, name, content)

        assert response.status_code == 202, response.text
        assert response.headers["Content-Location"] == f"{_JOBS}/{response.json()['id']}"
        pool.drain()
        state = _job_state(me, response.json()["id"])
        assert (state["kind"], state["status"], state["error_code"]) == ("activity_upload", "succeeded", None)
        (activity,) = activities_of(committed_sessions, me.user.id)
        assert state["activity_ids"] == [str(activity.id)]
        assert file_storage.get_activity_file(activity.id, storage) == (f"{activity.id}.{name.split('.')[-1]}", content)
        assert staged_keys(storage) == [], "the staged upload is consumed with the job"

    def test_a_fit_workout_step_without_a_duration_type_is_stored_without_one(self, me, pool, committed_sessions):
        # FIT duration type 0 is "time".
        response = _upload(me, "ride.fit", fit_file(workout_steps=(0, None)))
        pool.drain()

        assert _job_state(me, response.json()["id"])["status"] == "succeeded"
        (activity,) = activities_of(committed_sessions, me.user.id)
        steps = me.client.get(f"{_API}/activities/{activity.id}/workout-steps")
        assert steps.status_code == 200, steps.text
        stored = [(step["message_index"], step["duration_type"]) for step in steps.json()["items"]]
        assert stored == [(0, "time"), (1, None)]

    def test_leaves_nothing_in_the_incoming_directory(self, me, pool):
        _upload(me, "ride.gpx", activity_gpx())
        pool.drain()

        assert _incoming_files() == []

    def test_uploaded_twice_it_is_stored_once(self, me, pool, committed_sessions):
        first = _upload(me, "ride.gpx", activity_gpx())
        pool.drain()
        second = _upload(me, "again.gpx", activity_gpx())
        pool.drain()

        assert _job_state(me, second.json()["id"])["activity_ids"] == _job_state(me, first.json()["id"])["activity_ids"]
        assert len(activities_of(committed_sessions, me.user.id)) == 1

    def test_is_never_visible_to_another_user(self, me, make_signed_in, pool, committed_sessions):
        other = make_signed_in()
        response = _upload(me, "ride.gpx", activity_gpx())
        pool.drain()

        assert other.client.get(f"{_JOBS}/{response.json()['id']}").status_code == 404
        assert activities_of(committed_sessions, other.user.id) == []

    def test_tells_the_owner_once_the_outcome_is_committed(self, me, pool, committed_sessions, hints):
        response = _upload(me, "ride.gpx", activity_gpx())
        pool.drain()

        assert [hint["message"] for _key, hint in hints] == ["JOB_STATUS_CHANGED"]
        assert hints[0][1]["job_id"] == response.json()["id"]
        assert read_job(committed_sessions, uuid.UUID(response.json()["id"])).status == "completed"


class TestARefusedFile:
    def test_an_unsupported_extension_is_refused_before_any_job_or_blob_exists(
        self, me, pool, committed_sessions, storage
    ):
        response = _upload(me, "notes.txt", b"hello")

        assert response.status_code == 415
        assert response.json()["type"].endswith("unsupported-format")
        assert all_jobs(committed_sessions) == []
        assert staged_keys(storage) == []

    def test_content_that_is_not_the_named_format_is_refused_before_any_job_exists(
        self, me, pool, committed_sessions, storage
    ):
        response = _upload(me, "ride.gpx", b"this is not xml")

        assert response.status_code == 415
        assert all_jobs(committed_sessions) == []
        assert staged_keys(storage) == []
        assert _incoming_files() == []

    def test_a_truncated_fit_is_refused_before_any_job_exists(self, me, pool, committed_sessions):
        response = _upload(me, "ride.fit", fit_file()[:60])

        assert response.status_code == 415
        assert all_jobs(committed_sessions) == []

    def test_an_empty_file_is_a_bad_request(self, me, pool, committed_sessions):
        response = _upload(me, "ride.fit", b"")

        assert response.status_code == 400
        assert all_jobs(committed_sessions) == []


class TestAFileThatPassesTheSignatureCheckButIsNotAnActivity:
    @pytest.mark.parametrize(
        ("name", "content", "code"),
        [
            pytest.param("empty.gpx", EMPTY_GPX, _ErrorCode.INVALID_FILE, id="gpx-without-a-track"),
            pytest.param("nosession.fit", fit_file(with_session=False), _ErrorCode.NO_ACTIVITIES_FOUND, id="fit"),
        ],
    )
    def test_fails_its_job_with_a_specific_code_and_drops_the_staged_blob(
        self, me, pool, committed_sessions, storage, name, content, code
    ):
        response = _upload(me, name, content)
        assert response.status_code == 202
        pool.drain()
        state = _job_state(me, response.json()["id"])
        assert (state["status"], state["error_code"]) == ("failed", code.value)
        assert activities_of(committed_sessions, me.user.id) == []
        assert staged_keys(storage) == []

    def test_a_failed_job_tells_its_owner(self, me, pool, hints):
        _upload(me, "empty.gpx", EMPTY_GPX)
        pool.drain()

        assert [hint["message"] for _key, hint in hints] == ["JOB_STATUS_CHANGED"]


class TestAGzippedUpload:
    def test_is_decompressed_and_imported(self, me, pool, committed_sessions):
        response = _upload(me, "ride.gpx.gz", gzip.compress(activity_gpx()))
        pool.drain()

        assert _job_state(me, response.json()["id"])["status"] == "succeeded"
        assert len(activities_of(committed_sessions, me.user.id)) == 1

    @pytest.mark.parametrize("filename", ["ride.gz", "ride.txt.gz", "ride.gz.gz"])
    def test_a_gz_that_does_not_name_a_supported_format_is_refused_before_any_job_or_blob_exists(
        self, me, pool, committed_sessions, storage, filename
    ):
        """The inner format is read from the name (``ride.gpx.gz``), so one that names none could never import."""
        response = _upload(me, filename, gzip.compress(activity_gpx()))

        assert response.status_code == 415
        assert response.json()["type"].endswith("unsupported-format")
        assert all_jobs(committed_sessions) == []
        assert staged_keys(storage) == []


class TestABrokenServer:
    def test_a_storage_outage_while_staging_answers_503_with_retry_after_and_queues_nothing(
        self, me, pool, committed_sessions, break_storage, app_log
    ):
        break_storage(save_stream=StorageBackendUnavailableError("object storage is down"))

        response = _upload(me, "ride.gpx", activity_gpx())

        assert response.status_code == 503
        assert response.json()["type"].endswith("service-unavailable")
        assert response.headers["retry-after"] == "5"
        assert all_jobs(committed_sessions) == []
        assert _incoming_files() == []
        outage = [record for record in app_log.records if "StorageBackendUnavailableError" in record.getMessage()]
        assert [(record.levelname, record.exc_info) for record in outage] == [("WARNING", None)]

    def test_a_storage_outage_while_importing_fails_the_job_since_nothing_retries_it(
        self, me, pool, committed_sessions, break_storage
    ):
        break_storage(open_stream=StorageBackendUnavailableError("object storage is down"))

        response = _upload(me, "ride.gpx", activity_gpx())
        pool.drain()

        state = _job_state(me, response.json()["id"])
        assert (state["status"], state["error_code"]) == ("failed", _ErrorCode.PROCESSING_FAILED.value)
        assert activities_of(committed_sessions, me.user.id) == []

    def test_a_full_pool_refuses_the_upload_before_anything_is_staged(
        self, me, committed_sessions, storage, monkeypatch
    ):
        release = threading.Event()
        full = core_local_pool.BoundedPool("full", workers=1, max_pending=1)
        monkeypatch.setattr(ingestion_background, "_pool", full)
        full.submit(release.wait, 10)
        try:
            response = _upload(me, "ride.gpx", activity_gpx())
        finally:
            release.set()
            full.shutdown(wait=True)

        assert response.status_code == 503
        assert all_jobs(committed_sessions) == []
        assert staged_keys(storage) == []
        assert _incoming_files() == []


class TestStagingAnUpload:
    def test_a_storage_failure_while_staging_leaves_no_job_and_nothing_in_the_incoming_directory(
        self, me, committed_sessions, break_storage
    ):
        break_storage(save_stream=OSError("bucket is down"))

        with pytest.raises(OSError, match="bucket is down"):
            _upload(me, "ride.gpx", activity_gpx())

        assert all_jobs(committed_sessions) == []
        assert _incoming_files() == []

    def test_a_staged_upload_that_is_gone_when_the_job_runs_fails_it_as_an_invalid_file(
        self, me, pool, committed_sessions, storage, durable_jobs
    ):
        response = _upload(me, "ride.gpx", activity_gpx())
        job_id = uuid.UUID(response.json()["id"])
        for key in staged_keys(storage):
            storage.delete("activity_files", f"upload_staging/{key}")

        ingestion_service.run_upload_job(job_id, storage)

        row = read_job(committed_sessions, job_id)
        assert (row.status, row.error_code) == ("failed", "invalid_file")

    def test_the_job_runs_with_no_temporary_file_left_behind_on_any_outcome(self, me, pool, tmp_path, monkeypatch):
        scratch = tmp_path / "scratch"
        scratch.mkdir()
        monkeypatch.setattr(tempfile, "tempdir", str(scratch))

        _upload(me, "ride.gpx", activity_gpx())
        _upload(me, "empty.gpx", EMPTY_GPX)
        pool.drain()

        assert os.listdir(scratch) == []


class TestReceivingAnUpload:
    def test_a_request_without_a_filename_is_refused_before_anything_is_read(self, me, committed_sessions, storage):
        def never_called(**_options) -> str:
            raise AssertionError("the upload must not be read")

        with committed_sessions() as db, pytest.raises(core_exceptions.InvalidInputError):
            ingestion_service.accept_upload(me.user.id, None, never_called, storage, db)

        assert all_jobs(committed_sessions) == []

    def test_a_file_that_cannot_be_fingerprinted_is_not_left_behind_or_queued(self, me, committed_sessions, storage):
        def saves_nothing(*, kind, upload_dir, filename) -> str:
            return os.path.join(upload_dir, "never-written.gpx")

        with committed_sessions() as db, pytest.raises(OSError):
            ingestion_service.accept_upload(
                me.user.id, "ride.gpx", saves_nothing, storage, db, idempotency_key="needs-a-fingerprint"
            )

        assert all_jobs(committed_sessions) == []
        assert staged_keys(storage) == []
