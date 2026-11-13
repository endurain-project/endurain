"""Keyset listing of a user's ingestion jobs, where the row-value comparison runs in PostgreSQL."""

import uuid
from datetime import UTC, datetime, timedelta

import pytest

import core.job_status as core_job_status
import modules.activities.activity_ingestion.integration_service as ingestion_integration
import modules.activities.activity_ingestion.models as ingestion_models
from tests._helpers.auth import MOCK_USER_ID, OTHER_USER_ID
from tests._helpers.db import ensure_user

_USER_ID = MOCK_USER_ID
_NOW = datetime(2026, 7, 1, 12, 0, 0, tzinfo=UTC)
_ID_A, _ID_B, _ID_C, _ID_D = (uuid.UUID(f"00000000-0000-4000-8000-{number:012x}") for number in range(1, 5))
_ID_MINE_UPLOAD, _ID_MINE_REFRESH, _ID_THEIRS = (
    uuid.UUID(f"00000000-0000-4000-8000-0000000000b{number}") for number in range(1, 4)
)
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
    _add(factory, _ID_A, age_minutes=5)
    _add(factory, _ID_B, age_minutes=1)
    _add(factory, _ID_C, age_minutes=1)
    _add(factory, _ID_D, age_minutes=0)

    assert _list(factory) == [_ID_D, _ID_C, _ID_B, _ID_A]
    assert _list(factory, limit=2) == [_ID_D, _ID_C]
    assert _list(factory, before=(_NOW - timedelta(minutes=1), _ID_C)) == [_ID_B, _ID_A]
    assert _list(factory, before=(_NOW - timedelta(minutes=1), _ID_B)) == [_ID_A]


def test_filters_by_owner_kind_and_state(factory):
    _add(factory, _ID_MINE_UPLOAD, status="processing")
    _add(factory, _ID_MINE_REFRESH, kind="refresh", status="deferred", age_minutes=1)
    _add(factory, _ID_THEIRS, user_id=OTHER_USER_ID)

    assert _list(factory) == [_ID_MINE_UPLOAD, _ID_MINE_REFRESH]
    assert _list(factory, kinds={"activity_refresh"}) == [_ID_MINE_REFRESH]
    assert _list(factory, status=core_job_status.JobState.QUEUED) == [_ID_MINE_REFRESH]
    assert _list(factory, status=core_job_status.JobState.RUNNING) == [_ID_MINE_UPLOAD]


def test_read_job_is_scoped_to_the_owner(factory):
    _add(factory, _ID_THEIRS, user_id=OTHER_USER_ID)

    with factory() as db:
        assert ingestion_integration.read_job(_ID_THEIRS, _USER_ID, db) is None
        assert ingestion_integration.read_job(_ID_THEIRS, OTHER_USER_ID, db) is not None
