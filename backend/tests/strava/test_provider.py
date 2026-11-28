"""Strava as an activity provider: a refresh job asks it for a window and the stored activities come back."""

import uuid
from datetime import timedelta

import jasil.runtime as platform_runtime
import pytest
from sqlalchemy import select

import core.config as core_config
import core.database as core_database
import core.timezone as core_timezone
import modules.activities.activity.models as activity_models
import modules.activities.activity_ingestion.models as activity_ingestion_models
import modules.activities.activity_ingestion.provider_registry as provider_registry
import modules.activities.activity_ingestion.service as activity_ingestion_service
import modules.strava.integration_service as strava_integration
from tests._factories import strava as strava_factories
from tests._factories.users import make_user

_API = core_config.ROOT_PATH


@pytest.fixture(autouse=True)
def registered_strava(durable_jobs):
    """Register Strava with activity ingestion as startup does, on the durable profile so a job waits for the test."""
    provider_registry.clear()
    strava_integration.register_activity_provider()
    yield
    provider_registry.clear()


@pytest.fixture
def user(committed_sessions):
    with committed_sessions() as db:
        created = make_user(db)
        strava_factories.link_strava(db, created.id)
        db.commit()
    return created


def _request_range(sign_in, user) -> dict:
    today = core_timezone.today_in(core_timezone.or_default(None))
    response = sign_in(user).client.post(
        f"{_API}/strava/activities",
        params={
            "start_date": (today - timedelta(days=2)).isoformat(),
            "end_date": (today - timedelta(days=1)).isoformat(),
        },
    )
    assert response.status_code == 202, response.text
    return response.json()


def _run(job: dict) -> None:
    activity_ingestion_service.run_refresh_job(uuid.UUID(job["id"]), platform_runtime.get_active_platform().storage)


def _stored(user_id):
    with core_database.SessionLocal() as db:
        return list(
            db.scalars(
                select(activity_models.ActivitySource.provider_id).where(
                    activity_models.ActivitySource.user_id == user_id, activity_models.ActivitySource.kind == "strava"
                )
            )
        )


def test_a_refresh_job_stores_the_activities_strava_returns_for_the_window(sign_in, user, strava):
    strava.on("GET", "/athlete/activities", strava_factories.ok([strava_factories.summary_activity(1001)]))
    strava.on("GET", "/activities/1001", strava_factories.ok(strava_factories.detailed_activity(1001)))
    strava.on("GET", "/activities/1001/streams", strava_factories.refused(404))
    strava.on("GET", "/activities/1001/laps", strava_factories.ok([]))
    job = _request_range(sign_in, user)

    _run(job)

    assert _stored(user.id) == [1001]
    finished = sign_in(user).client.get(f"{_API}/jobs/{job['id']}")
    assert (finished.json()["status"], len(finished.json()["activity_ids"])) == ("succeeded", 1)


def test_a_rate_limited_application_defers_the_job_until_the_limit_clears(
    sign_in, user, strava, rate_limits, committed_sessions
):
    strava.on("GET", "/athlete/activities", strava_factories.rate_limited())
    job = _request_range(sign_in, user)

    _run(job)

    with committed_sessions() as db:
        row = db.get(activity_ingestion_models.ActivityIngestionJob, uuid.UUID(job["id"]))
    assert row.retry_after == rate_limits.rate_limited_until(strava_factories.CLIENT_ID)
    assert sign_in(user).client.get(f"{_API}/jobs/{job['id']}").json()["status"] == "queued"
    assert _stored(user.id) == []


def test_a_user_who_is_not_linked_is_not_called_for(sign_in, committed_sessions, strava):
    with committed_sessions() as db:
        unlinked = make_user(db)
        db.commit()
    job = _request_range(sign_in, unlinked)

    _run(job)

    assert strava.calls == []
    assert _stored(unlinked.id) == []


def test_users_who_linked_strava_are_the_ones_the_provider_lists(user, committed_sessions):
    with committed_sessions() as db:
        make_user(db)
        db.commit()

    (provider,) = provider_registry.registered()

    assert user.id in provider.linked_user_ids(None, 1000)
