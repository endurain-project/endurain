"""Every ``202`` names the job it started and when to poll it, and a refused second start names the running job.

The routes run on the production application, so the assertions read what a client sees: the ``Content-Location``
path, ``Retry-After`` and the ``409`` that names the running job. Reading a job, and its ``Retry-After`` while it
runs, is tested with the job routes. The Garmin Connect and Strava starts need a provider account and a worker pool;
their tests (``tests/garmin``, ``tests/strava``) run them with a fake provider.
"""

from datetime import UTC, datetime

import pytest

import core.config as core_config
import modules.activities.activity.bulk_edit_constants as bulk_edit_constants
import modules.activities.activity_ingestion.constants as ingestion_constants
import modules.gears.gear.constants as gears_constants
import modules.users.users.constants as users_constants
import modules.users.users_profile.constants as profile_constants
from tests._factories.garmin import activity_gpx, zip_of
from tests._factories.gears import make_gear
from tests._factories.jobs import make_ingestion_job, make_ingestion_job_at
from tests._factories.users import PASSWORD, make_admin, make_user

_API = core_config.ROOT_PATH
_STEP_UP = {"step_up": {"current_password": PASSWORD}}
_JOBS = f"{_API}/jobs"
_Kind = ingestion_constants.IngestionJobKind


@pytest.fixture
def me(sign_in, committed_sessions):
    """A signed-in regular user."""
    with committed_sessions() as db:
        user = make_user(db, timezone="UTC")
        db.commit()
    return sign_in(user)


def _own_gear(me, committed_sessions):
    with committed_sessions() as db:
        gear = make_gear(db, me.user.id)
        db.commit()
    return gear.id


def _delete_gear(client, gear_id):
    etag = client.get(f"{_API}/gears/{gear_id}").headers["ETag"]
    return client.delete(f"{_API}/gears/{gear_id}", headers={"If-Match": etag})


def _upload(me, **_):
    return me.client.post(f"{_API}/activities/upload", files={"file": ("ride.gpx", activity_gpx())})


def _bulk_import(me, **_):
    archive = zip_of({"ride.gpx": activity_gpx()})
    return me.client.post(f"{_API}/activities/bulk-import", files={"file": ("export.zip", archive)})


def _refresh(me, **_):
    return me.client.post(f"{_API}/activities/refresh")


def _bulk_edit(me, **_):
    return me.client.patch(f"{_API}/activities", json={"visibility": "private"})


def _gear_deletion(me, committed_sessions, **_):
    return _delete_gear(me.client, _own_gear(me, committed_sessions))


def _profile_export(me, **_):
    return me.client.post(f"{_API}/profile/export", json=_STEP_UP)


def _profile_import(me, **_):
    archive = zip_of({"data/activities.json": b"[]"})
    return me.client.post(f"{_API}/profile/import", files={"file": ("export.zip", archive)})


def _user_deletion(me, committed_sessions, sign_in):
    with committed_sessions() as db:
        admin = make_admin(db)
        target = make_user(db)
        db.commit()
    client = sign_in(admin).client
    etag = client.get(f"{_API}/users/{target.id}").headers["ETag"]
    return client.post(f"{_API}/users/{target.id}/delete", json=_STEP_UP, headers={"If-Match": etag})


#: ``(route, kind it starts, Retry-After)`` of every ``202`` that names a status.
_ACCEPTING_ROUTES = [
    pytest.param(_upload, "activity_upload", ingestion_constants.JOB_POLL_SECONDS[_Kind.UPLOAD], id="upload"),
    pytest.param(
        _bulk_import,
        "activity_bulk_import",
        ingestion_constants.JOB_POLL_SECONDS[_Kind.BULK_IMPORT],
        id="bulk-import",
    ),
    pytest.param(_refresh, "activity_refresh", ingestion_constants.JOB_POLL_SECONDS[_Kind.REFRESH], id="refresh"),
    pytest.param(_bulk_edit, "activities_bulk_edit", bulk_edit_constants.BULK_EDIT_POLL_SECONDS, id="bulk-edit"),
    pytest.param(_gear_deletion, "gear_deletion", gears_constants.DELETION_POLL_SECONDS, id="gear-deletion"),
    pytest.param(_profile_export, "profile_export", profile_constants.EXPORT_POLL_SECONDS, id="profile-export"),
    pytest.param(_profile_import, "profile_import", profile_constants.IMPORT_POLL_SECONDS, id="profile-import"),
    pytest.param(_user_deletion, "user_deletion", users_constants.DELETION_POLL_SECONDS, id="user-deletion"),
]


@pytest.mark.parametrize(("start", "kind", "retry_after"), _ACCEPTING_ROUTES)
def test_a_202_names_its_job_and_when_to_poll_it(me, committed_sessions, sign_in, start, kind, retry_after):
    response = start(me, committed_sessions=committed_sessions, sign_in=sign_in)

    assert response.status_code == 202, response.text
    body = response.json()
    assert body["kind"] == kind
    assert response.headers["Content-Location"] == f"{_JOBS}/{body['id']}"
    assert response.headers["Retry-After"] == str(retry_after)


def test_an_account_deletion_by_its_owner_names_no_job_to_read(me):
    response = me.client.post(f"{_API}/profile/delete-account", json=_STEP_UP)

    assert response.status_code == 202, response.text
    assert response.json()["kind"] == "user_deletion"
    assert "Content-Location" not in response.headers


class TestARefusedSecondRun:
    def test_a_second_bulk_import_names_the_running_job(self, me, committed_sessions):
        """The first import is arranged unfinished: a real one can finish before the second request arrives."""
        with committed_sessions() as db:
            running = make_ingestion_job_at(
                db, me.user.id, datetime.now(UTC), kind=ingestion_constants.IngestionJobKind.BULK_IMPORT
            )
            db.commit()

        response = me.client.post(f"{_API}/activities/bulk-import/folder")

        assert response.status_code == 409
        assert response.headers["Content-Location"] == f"{_JOBS}/{running.id}"
        assert response.headers["Content-Type"].startswith("application/problem+json")
        body = response.json()
        assert body["type"].endswith(":conflict")
        assert body["job_id"] == str(running.id)

    def test_a_conflict_that_is_no_running_job_carries_no_location(self, me, committed_sessions):
        with committed_sessions() as db:
            for _ in range(ingestion_constants.MAX_OPEN_UPLOADS_PER_USER):
                make_ingestion_job(db, me.user.id)
            db.commit()

        response = _upload(me)

        assert response.status_code == 409
        assert "Content-Location" not in response.headers
        assert "job_id" not in response.json()
