"""The job routes through the production application: ``GET /jobs/{job_id}``, ``GET /jobs`` and the ``409`` that
points at a running job."""

import uuid

import jasil.runtime as jasil_runtime
import pytest

import core.config as core_config
import core.job_status as core_job_status
import modules.auth.api_keys.constants as api_keys_constants
import modules.strava.constants as strava_constants
import modules.strava.sync_state_store as strava_sync_state_store
from tests._factories.api_keys import key_client, make_api_key
from tests._factories.jobs import make_bulk_edit_job, make_ingestion_job
from tests._factories.users import make_user

_JOBS = f"{core_config.ROOT_PATH}/jobs"
Status = core_job_status.JobState


@pytest.fixture
def user(committed_sessions):
    with committed_sessions() as db:
        created = make_user(db)
        db.commit()
    return created


@pytest.fixture
def signed_in(sign_in, user):
    return sign_in(user)


def _gear_sync(user_id):
    """Queue a Strava gear sync as its route does, in the platform's state store."""
    return strava_sync_state_store.StravaSyncStateStore(jasil_runtime.get_active_platform().state).begin(
        user_id, strava_constants.SyncKind.GEAR, conflict="Busy"
    )


class TestReadJob:
    def test_a_running_job_is_read_with_its_kind_and_asks_to_be_polled(self, signed_in):
        job = _gear_sync(signed_in.user.id)

        response = signed_in.client.get(f"{_JOBS}/{job.id}")

        assert response.status_code == 200
        body = response.json()
        assert (body["id"], body["kind"], body["status"]) == (str(job.id), "strava_gear", "queued")
        assert response.headers["Retry-After"] == str(
            strava_constants.SYNC_POLL_SECONDS[strava_constants.SyncKind.GEAR]
        )

    def test_a_finished_job_is_not_polled_again(self, signed_in):
        job = _gear_sync(signed_in.user.id)
        strava_sync_state_store.StravaSyncStateStore(jasil_runtime.get_active_platform().state).set_status(
            signed_in.user.id, strava_constants.SyncKind.GEAR, Status.SUCCEEDED, job_id=job.id
        )

        response = signed_in.client.get(f"{_JOBS}/{job.id}")

        assert response.json()["status"] == "succeeded"
        assert response.json()["finished_at"] is not None
        assert "Retry-After" not in response.headers

    def test_an_activity_upload_is_read_from_the_database(self, signed_in, committed_sessions):
        with committed_sessions() as db:
            upload = make_ingestion_job(db, signed_in.user.id)
            db.commit()

        response = signed_in.client.get(f"{_JOBS}/{upload.id}")

        assert response.status_code == 200
        assert (response.json()["id"], response.json()["kind"]) == (str(upload.id), "activity_upload")

    def test_a_job_read_without_the_scope_its_kind_needs_is_forbidden(self, app, committed_sessions, user):
        job = _gear_sync(user.id)
        with committed_sessions() as db:
            key, raw_key = make_api_key(db, user, scopes=[api_keys_constants.ApiKeyScope.ACTIVITIES_UPLOAD])
            db.commit()
        holder = key_client(app, user, key, raw_key)

        assert holder.client.get(f"{_JOBS}/{job.id}").status_code == 403

    def test_another_users_job_and_an_unknown_id_are_not_found(self, signed_in, committed_sessions):
        with committed_sessions() as db:
            other = make_user(db)
            upload = make_ingestion_job(db, other.id)
            db.commit()
        gear = _gear_sync(other.id)

        for job_id in (gear.id, upload.id, uuid.uuid4()):
            assert signed_in.client.get(f"{_JOBS}/{job_id}").status_code == 404

    def test_an_id_that_is_not_a_uuid_is_refused(self, signed_in):
        assert signed_in.client.get(f"{_JOBS}/not-a-uuid").status_code == 422


class TestListJobs:
    def test_the_callers_jobs_are_listed_and_filtered(self, signed_in, committed_sessions):
        gear = _gear_sync(signed_in.user.id)
        with committed_sessions() as db:
            upload = make_ingestion_job(db, signed_in.user.id)
            db.commit()

        everything = signed_in.client.get(_JOBS)
        gears = signed_in.client.get(_JOBS, params={"kind": "strava_gear", "status": "queued"})

        assert {item["id"] for item in everything.json()["items"]} == {str(gear.id), str(upload.id)}
        assert [item["id"] for item in gears.json()["items"]] == [str(gear.id)]
        assert gears.json()["next_cursor"] is None

    def test_a_key_lists_only_the_kinds_its_scopes_allow(self, app, committed_sessions, user):
        _gear_sync(user.id)
        with committed_sessions() as db:
            upload = make_ingestion_job(db, user.id)
            key, raw_key = make_api_key(db, user, scopes=[api_keys_constants.ApiKeyScope.ACTIVITIES_UPLOAD])
            db.commit()
        holder = key_client(app, user, key, raw_key)

        response = holder.client.get(_JOBS)

        assert [item["id"] for item in response.json()["items"]] == [str(upload.id)]

    def test_the_list_is_paged_by_cursor(self, signed_in):
        first = _gear_sync(signed_in.user.id)
        second = strava_sync_state_store.StravaSyncStateStore(jasil_runtime.get_active_platform().state).begin(
            signed_in.user.id, strava_constants.SyncKind.LINK, conflict="Busy"
        )

        page = signed_in.client.get(_JOBS, params={"num_records": 1}).json()
        rest = signed_in.client.get(_JOBS, params={"num_records": 1, "cursor": page["next_cursor"]}).json()

        assert [item["id"] for item in page["items"]] == [str(second.id)]
        assert [item["id"] for item in rest["items"]] == [str(first.id)]
        assert rest["next_cursor"] is None

    def test_a_cursor_this_server_did_not_issue_is_refused(self, signed_in):
        assert signed_in.client.get(_JOBS, params={"cursor": "not-a-cursor"}).status_code == 400

    def test_an_unknown_kind_is_refused(self, signed_in):
        assert signed_in.client.get(_JOBS, params={"kind": "nope"}).status_code == 422


def test_a_refused_second_start_points_at_the_running_job(signed_in):
    running = make_bulk_edit_job(signed_in.user.id)

    response = signed_in.client.patch(f"{core_config.ROOT_PATH}/activities", json={"visibility": "public"})

    assert response.status_code == 409
    job_id = response.json()["job_id"]
    assert job_id == str(running)
    assert response.headers["Content-Location"] == f"{_JOBS}/{job_id}"
    assert signed_in.client.get(f"{_JOBS}/{job_id}").json()["kind"] == "activities_bulk_edit"
