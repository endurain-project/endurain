"""Reading and listing a user's ingestion jobs; the keyset comparison on ``(created_at, id)`` runs in PostgreSQL."""

import uuid
from datetime import UTC, datetime, timedelta

import pytest

import core.job_status as core_job_status
import modules.activities.activity_ingestion.constants as ingestion_constants
import modules.activities.activity_ingestion.integration_service as ingestion_integration
from tests._factories.ingestion import stage_job
from tests._factories.users import make_user

_NOW = datetime(2026, 7, 1, 12, 0, 0, tzinfo=UTC)
_State = core_job_status.JobState
_Kind = ingestion_constants.IngestionJobKind
_ALL_KINDS = {"activity_upload", "activity_refresh", "activity_bulk_import"}


def _uid(number: int) -> uuid.UUID:
    """Build a stable id whose ordering follows ``number``."""
    return uuid.UUID(f"00000000-0000-4000-8000-{number:012x}")


def _add(db, user, number: int, *, age_minutes: int = 0, kind=_Kind.UPLOAD, status: str = "pending", **options):
    options.setdefault("import_source", "generic" if kind is _Kind.BULK_IMPORT else None)
    return stage_job(
        db,
        user.id,
        job_id=_uid(number),
        created_at=_NOW - timedelta(minutes=age_minutes),
        kind=kind,
        status=status,
        **options,
    )


def _listed(db, user, **overrides) -> list[uuid.UUID]:
    args = {"kinds": _ALL_KINDS, "status": None, "before": None, "limit": 10} | overrides
    return [job.id for job in ingestion_integration.list_jobs(user.id, db, **args)]


class TestReadJob:
    def test_returns_the_callers_job_with_its_flat_kind(self, db):
        user = make_user(db)
        _add(db, user, 1, kind=_Kind.BULK_IMPORT)

        job = ingestion_integration.read_job(_uid(1), user.id, db)

        assert job is not None
        assert (job.id, job.kind, job.status) == (_uid(1), "activity_bulk_import", _State.QUEUED)

    def test_a_missing_job_is_none(self, db):
        assert ingestion_integration.read_job(_uid(9), make_user(db).id, db) is None

    def test_another_users_job_is_none_for_the_caller_and_visible_to_its_owner(self, db):
        user, stranger = make_user(db), make_user(db)
        _add(db, stranger, 1)

        assert ingestion_integration.read_job(_uid(1), user.id, db) is None
        assert ingestion_integration.read_job(_uid(1), stranger.id, db) is not None


class TestListJobs:
    def test_lists_newest_first_and_pages_without_gaps_or_repeats_across_equal_timestamps(self, db):
        user = make_user(db)
        _add(db, user, 1, age_minutes=5)
        _add(db, user, 2, age_minutes=1)
        _add(db, user, 3, age_minutes=1)
        _add(db, user, 4, age_minutes=0)
        one_minute_ago = _NOW - timedelta(minutes=1)

        assert _listed(db, user) == [_uid(4), _uid(3), _uid(2), _uid(1)]
        assert _listed(db, user, limit=2) == [_uid(4), _uid(3)]
        assert _listed(db, user, before=(one_minute_ago, _uid(3))) == [_uid(2), _uid(1)]
        assert _listed(db, user, before=(one_minute_ago, _uid(2))) == [_uid(1)]

    def test_only_the_callers_jobs_are_listed(self, db):
        user, stranger = make_user(db), make_user(db)
        _add(db, user, 1)
        _add(db, stranger, 2)

        assert _listed(db, user) == [_uid(1)]

    def test_filters_by_flat_kind(self, db):
        user = make_user(db)
        _add(db, user, 1)
        _add(db, user, 2, kind=_Kind.REFRESH, age_minutes=1)
        _add(db, user, 3, kind=_Kind.BULK_IMPORT, age_minutes=2)

        jobs = ingestion_integration.list_jobs(
            user.id,
            db,
            kinds={"activity_refresh", "activity_bulk_import"},
            status=None,
            before=None,
            limit=10,
        )

        assert [job.id for job in jobs] == [_uid(2), _uid(3)]
        assert [job.kind for job in jobs] == ["activity_refresh", "activity_bulk_import"]

    def test_no_kinds_lists_nothing(self, db):
        user = make_user(db)
        _add(db, user, 1)

        assert _listed(db, user, kinds=set()) == []

    @pytest.mark.parametrize(
        ("state", "expected"),
        [
            (_State.QUEUED, ["pending", "deferred"]),
            (_State.RUNNING, ["processing"]),
            (_State.SUCCEEDED, ["completed"]),
            (_State.FAILED, ["failed"]),
        ],
    )
    def test_filters_by_the_state_a_client_reads(self, db, state, expected):
        user = make_user(db)
        stored_states = ["pending", "deferred", "processing", "completed", "failed"]
        for index, stored in enumerate(stored_states):
            _add(db, user, index + 1, status=stored, age_minutes=index)

        assert set(_listed(db, user, status=state)) == {_uid(stored_states.index(stored) + 1) for stored in expected}

    def test_limit_caps_the_rows(self, db):
        user = make_user(db)
        for index in range(4):
            _add(db, user, index + 1, age_minutes=index)

        assert _listed(db, user, limit=2) == [_uid(1), _uid(2)]
