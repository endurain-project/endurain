"""Reading and listing a user's ingestion jobs through the integration surface, against SQLite."""

from datetime import UTC, datetime, timedelta

import pytest
from tests._helpers.auth import MOCK_USER_ID, OTHER_USER_ID
from tests._helpers.db import create_sqlite_session_factory, ensure_user

import core.job_status as core_job_status
import modules.activities.activity_ingestion.integration_service as ingestion_integration
import modules.activities.activity_ingestion.models as ingestion_models

_NOW = datetime(2026, 7, 1, 12, 0, 0, tzinfo=UTC)
_State = core_job_status.JobState


@pytest.fixture
def factory():
    session_factory = create_sqlite_session_factory()
    try:
        yield session_factory
    finally:
        session_factory.kw["bind"].dispose()


def _add(factory, job_id, *, user_id=MOCK_USER_ID, kind="upload", status="pending", age_minutes=0):
    ensure_user(factory, user_id)
    created = _NOW - timedelta(minutes=age_minutes)
    with factory() as db:
        db.add(
            ingestion_models.ActivityIngestionJob(
                id=job_id, user_id=user_id, kind=kind, status=status, created_at=created, updated_at=created
            )
        )
        db.commit()


def _ids(jobs):
    return [job.id for job in jobs]


class TestReadJob:
    def test_returns_the_callers_job_with_its_flat_kind(self, factory):
        _add(factory, "job-1", kind="bulk_import")

        with factory() as db:
            job = ingestion_integration.read_job("job-1", MOCK_USER_ID, db)

        assert job is not None
        assert (job.id, job.kind, job.status) == ("job-1", "activity_bulk_import", _State.QUEUED)

    def test_a_missing_job_is_none(self, factory):
        with factory() as db:
            assert ingestion_integration.read_job("nope", MOCK_USER_ID, db) is None

    def test_another_users_job_is_none(self, factory):
        _add(factory, "job-1", user_id=OTHER_USER_ID)
        ensure_user(factory, MOCK_USER_ID)

        with factory() as db:
            assert ingestion_integration.read_job("job-1", MOCK_USER_ID, db) is None


class TestListJobs:
    def _list(self, factory, **overrides):
        args = {"kinds": {"activity_upload", "activity_refresh", "activity_bulk_import"}, "status": None}
        args |= {"before": None, "limit": 10} | overrides
        with factory() as db:
            return ingestion_integration.list_jobs(MOCK_USER_ID, db, **args)

    def test_lists_newest_first_with_the_id_as_tiebreak(self, factory):
        _add(factory, "a", age_minutes=5)
        _add(factory, "b", age_minutes=1)
        _add(factory, "c", age_minutes=1)

        assert _ids(self._list(factory)) == ["c", "b", "a"]

    def test_only_the_callers_jobs_are_listed(self, factory):
        _add(factory, "mine")
        _add(factory, "theirs", user_id=OTHER_USER_ID)

        assert _ids(self._list(factory)) == ["mine"]

    def test_filters_by_flat_kind(self, factory):
        _add(factory, "u", kind="upload")
        _add(factory, "r", kind="refresh", age_minutes=1)
        _add(factory, "b", kind="bulk_import", age_minutes=2)

        jobs = self._list(factory, kinds={"activity_refresh", "activity_bulk_import"})

        assert _ids(jobs) == ["r", "b"]
        assert [job.kind for job in jobs] == ["activity_refresh", "activity_bulk_import"]

    def test_no_kinds_lists_nothing(self, factory):
        _add(factory, "u")

        assert self._list(factory, kinds=set()) == []

    @pytest.mark.parametrize(
        ("state", "expected"),
        [
            (_State.QUEUED, ["pending", "deferred"]),
            (_State.RUNNING, ["processing"]),
            (_State.SUCCEEDED, ["completed"]),
            (_State.FAILED, ["failed"]),
        ],
    )
    def test_filters_by_the_state_a_client_reads(self, factory, state, expected):
        for index, stored in enumerate(["pending", "deferred", "processing", "completed", "failed"]):
            _add(factory, stored, status=stored, age_minutes=index)

        assert sorted(_ids(self._list(factory, status=state))) == sorted(expected)

    def test_before_keeps_only_rows_strictly_older_than_the_position(self, factory):
        _add(factory, "a", age_minutes=5)
        _add(factory, "b", age_minutes=1)
        _add(factory, "c", age_minutes=1)
        _add(factory, "d", age_minutes=0)

        page = self._list(factory, before=(_NOW - timedelta(minutes=1), "c"))

        assert _ids(page) == ["b", "a"]

    def test_limit_caps_the_rows(self, factory):
        for index in range(4):
            _add(factory, f"j{index}", age_minutes=index)

        assert _ids(self._list(factory, limit=2)) == ["j0", "j1"]


class TestSetJobLocation:
    @pytest.mark.parametrize(("kind", "seconds"), [("activity_upload", "2"), ("activity_refresh", "5")])
    def test_names_the_job_and_the_wait_for_its_kind(self, kind, seconds):
        from fastapi import FastAPI, Request, Response
        from fastapi.testclient import TestClient

        import modules.activities.activity_ingestion.schema as ingestion_schema

        app = FastAPI()
        app.add_api_route("/jobs/{job_id}", lambda job_id: None, name="read_job")

        @app.post("/start")
        def start(request: Request, response: Response) -> None:
            job = ingestion_schema.ActivityIngestionJobRead(
                id="job-9", kind=kind, status=_State.QUEUED, created_at=_NOW, updated_at=_NOW
            )
            ingestion_integration.set_job_location(response, request, job)

        response = TestClient(app).post("/start")

        assert response.headers["Content-Location"] == "/jobs/job-9"
        assert response.headers["Retry-After"] == seconds
