"""Keyset listing of a user's ingestion jobs, where the row-value comparison runs in PostgreSQL."""

from datetime import UTC, datetime, timedelta

import pytest

import core.job_status as core_job_status
import modules.activities.activity_ingestion.integration_service as ingestion_integration
import modules.activities.activity_ingestion.models as ingestion_models
from tests._helpers.auth import MOCK_USER_ID, OTHER_USER_ID
from tests._helpers.db import ensure_user

_USER_ID = MOCK_USER_ID
_NOW = datetime(2026, 7, 1, 12, 0, 0, tzinfo=UTC)
_KINDS = {"activity_upload", "activity_refresh", "activity_bulk_import"}


@pytest.fixture
def factory(pg_factory):
    ensure_user(pg_factory, _USER_ID)
    ensure_user(pg_factory, OTHER_USER_ID)
    return pg_factory


def _add(factory, job_id, *, user_id=_USER_ID, kind="upload", status="pending", age_minutes=0):
    created = _NOW - timedelta(minutes=age_minutes)
    with factory() as db:
        db.add(
            ingestion_models.ActivityIngestionJob(
                id=job_id, user_id=user_id, kind=kind, status=status, created_at=created, updated_at=created
            )
        )
        db.commit()


def _list(factory, **overrides):
    args = {"kinds": _KINDS, "status": None, "before": None, "limit": 10} | overrides
    with factory() as db:
        return [job.id for job in ingestion_integration.list_jobs(_USER_ID, db, **args)]


def test_lists_newest_first_and_pages_without_gaps_or_repeats_across_equal_timestamps(factory):
    _add(factory, "a", age_minutes=5)
    _add(factory, "b", age_minutes=1)
    _add(factory, "c", age_minutes=1)
    _add(factory, "d", age_minutes=0)

    assert _list(factory) == ["d", "c", "b", "a"]
    assert _list(factory, limit=2) == ["d", "c"]
    assert _list(factory, before=(_NOW - timedelta(minutes=1), "c")) == ["b", "a"]
    assert _list(factory, before=(_NOW - timedelta(minutes=1), "b")) == ["a"]


def test_filters_by_owner_kind_and_state(factory):
    _add(factory, "mine-upload", status="processing")
    _add(factory, "mine-refresh", kind="refresh", status="deferred", age_minutes=1)
    _add(factory, "theirs", user_id=OTHER_USER_ID)

    assert _list(factory) == ["mine-upload", "mine-refresh"]
    assert _list(factory, kinds={"activity_refresh"}) == ["mine-refresh"]
    assert _list(factory, status=core_job_status.JobState.QUEUED) == ["mine-refresh"]
    assert _list(factory, status=core_job_status.JobState.RUNNING) == ["mine-upload"]


def test_read_job_is_scoped_to_the_owner(factory):
    _add(factory, "theirs", user_id=OTHER_USER_ID)

    with factory() as db:
        assert ingestion_integration.read_job("theirs", _USER_ID, db) is None
        assert ingestion_integration.read_job("theirs", OTHER_USER_ID, db) is not None
