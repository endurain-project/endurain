"""Tests for finding and listing background jobs across the features that own them."""

import typing
import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock, patch

import pytest
from jasil.backends.state_memory import MemoryState

import core.attempt_state as core_attempt_state
import core.exceptions as core_exceptions
import core.job_status as core_job_status
import modules.activities.activity_ingestion.schema as activity_ingestion_schema
import modules.garmin.link_state_store as garmin_link_state_store
import modules.jobs.schema as jobs_schema
import modules.jobs.service as jobs_service
import modules.strava.constants as strava_constants
import modules.strava.sync_state_store as strava_sync_state_store
import modules.users.users.constants as users_constants
import modules.users.users.deletion_state_store as deletion_state_store

USER = uuid.UUID("2f6d8b52-47a0-4c3e-9a51-0c1e5d7b8a90")
OTHER_USER = uuid.UUID("7b1c93e4-5d28-4f6a-8e03-a94d2c6f1b57")
THIRD_USER = uuid.UUID("c3a85f19-0e72-4b4d-b6a8-3d9e17f4c250")
UPLOAD_1 = uuid.UUID("a1000000-0000-4000-8000-000000000001")
UPLOAD_OLD = uuid.UUID("a1000000-0000-4000-8000-000000000002")
UPLOAD_NEW = uuid.UUID("a1000000-0000-4000-8000-000000000003")
MISSING_JOB = uuid.UUID("a1000000-0000-4000-8000-000000000004")
ODD_JOB = uuid.UUID("a1000000-0000-4000-8000-000000000005")

Status = core_job_status.JobState
_ALL = frozenset({"account", "account:integrations", "activities:upload", "users:read-all"})
_INGESTION_READ = "modules.activities.activity_ingestion.integration_service.read_job"
_INGESTION_LIST = "modules.activities.activity_ingestion.integration_service.list_jobs"


@pytest.fixture
def state():
    return MemoryState()


def _strava(state, user_id=USER, kind=strava_constants.SyncKind.GEAR):
    return strava_sync_state_store.StravaSyncStateStore(state).begin(user_id, kind, conflict="Busy")


def _upload(job_id: uuid.UUID, created_at: datetime) -> activity_ingestion_schema.ActivityIngestionJobRead:
    return activity_ingestion_schema.ActivityIngestionJobRead(
        id=job_id,
        kind="activity_upload",
        status=Status.SUCCEEDED,
        created_at=created_at,
        updated_at=created_at,
    )


class TestGetJob:
    def test_the_owner_reads_a_state_store_job_with_its_rule(self, state):
        job = _strava(state)

        view = jobs_service.get_job(job.id, USER, _ALL, state, MagicMock())

        assert view.job.id == job.id
        assert view.job.kind == "strava_gear"
        assert view.job.status == Status.QUEUED
        assert view.scope == "account"
        assert view.poll_seconds == strava_constants.SYNC_POLL_SECONDS[strava_constants.SyncKind.GEAR]

    @pytest.mark.parametrize("kind", [strava_constants.SyncKind.LINK, strava_constants.SyncKind.UNLINK])
    def test_a_strava_link_or_unlink_job_is_read_with_the_integrations_scope(self, state, kind):
        job = _strava(state, kind=kind)

        view = jobs_service.get_job(job.id, USER, _ALL, state, MagicMock())

        assert view.scope == "account:integrations"

    def test_a_garmin_link_job_is_read_with_the_integrations_scope(self, state):
        job = garmin_link_state_store.GarminLinkStateStore(state).begin(USER, conflict="Busy")

        view = jobs_service.get_job(job.id, USER, _ALL, state, MagicMock())

        assert view.scope == "account:integrations"

    def test_another_users_job_is_not_found(self, state):
        job = _strava(state, user_id=OTHER_USER)

        with pytest.raises(core_exceptions.NotFoundError):
            jobs_service.get_job(job.id, USER, _ALL, state, MagicMock())

    def test_a_job_its_subject_has_replaced_is_not_found(self, state):
        first = _strava(state)
        strava_sync_state_store.StravaSyncStateStore(state).set_status(
            USER, strava_constants.SyncKind.GEAR, Status.SUCCEEDED
        )
        _strava(state)

        with pytest.raises(core_exceptions.NotFoundError):
            jobs_service.get_job(first.id, USER, _ALL, state, MagicMock())

    def test_an_id_the_index_does_not_hold_is_read_as_an_ingestion_job(self, state):
        upload = _upload(UPLOAD_1, datetime(2026, 1, 1, tzinfo=UTC))
        db = MagicMock()
        with patch(_INGESTION_READ, return_value=upload) as read:
            view = jobs_service.get_job(UPLOAD_1, USER, _ALL, state, db)

        read.assert_called_once_with(UPLOAD_1, USER, db)
        assert view.job is upload
        assert view.scope == "activities:upload"

    def test_an_unknown_id_is_not_found(self, state):
        with patch(_INGESTION_READ, return_value=None), pytest.raises(core_exceptions.NotFoundError):
            jobs_service.get_job(MISSING_JOB, USER, _ALL, state, MagicMock())

    def test_an_indexed_job_of_a_kind_no_feature_reads_is_not_found(self, state):
        core_attempt_state.JobIndex(state).put(
            core_job_status.JobRef(
                id=ODD_JOB, kind="retired_kind", owner_id=USER, subject=str(USER), created_at=datetime.now(UTC)
            ),
            60,
        )

        with pytest.raises(core_exceptions.NotFoundError):
            jobs_service.get_job(ODD_JOB, USER, _ALL, state, MagicMock())

    def test_any_holder_of_users_read_all_follows_an_account_deletion(self, state):
        job = deletion_state_store.UserDeletionStateStore(state).begin(
            THIRD_USER, users_constants.DeletionKind.ACCOUNT, conflict="Busy", owner_id=USER
        )

        view = jobs_service.get_job(job.id, OTHER_USER, {"users:read-all"}, state, MagicMock())

        assert view.job.kind == "user_deletion"
        with pytest.raises(core_exceptions.NotFoundError):
            jobs_service.get_job(job.id, OTHER_USER, {"account"}, state, MagicMock())


class TestListJobs:
    def test_state_store_and_ingestion_jobs_are_merged_newest_first_and_paged(self, state):
        gear = _strava(state)
        link = _strava(state, kind=strava_constants.SyncKind.LINK)
        old = _upload(UPLOAD_OLD, gear.created_at - timedelta(days=1))
        new = _upload(UPLOAD_NEW, link.created_at + timedelta(days=1))
        with patch(_INGESTION_LIST, return_value=[new, old]) as ingestion:
            first = jobs_service.list_jobs(
                USER, _ALL, state, MagicMock(), kind=None, status=None, cursor=None, num_records=2
            )

        assert [job.id for job in first.items] == [UPLOAD_NEW, link.id]
        assert first.next_cursor is not None
        assert ingestion.call_args.kwargs["before"] is None
        assert ingestion.call_args.kwargs["limit"] == 3

        with patch(_INGESTION_LIST, return_value=[old]) as ingestion:
            second = jobs_service.list_jobs(
                USER, _ALL, state, MagicMock(), kind=None, status=None, cursor=first.next_cursor, num_records=2
            )

        assert ingestion.call_args.kwargs["before"] == (link.created_at, link.id)
        assert [job.id for job in second.items] == [gear.id, UPLOAD_OLD]
        assert second.next_cursor is None

    def test_a_link_job_is_not_listed_without_the_integrations_scope(self, state):
        _strava(state, kind=strava_constants.SyncKind.LINK)

        with patch(_INGESTION_LIST, return_value=[]):
            page = jobs_service.list_jobs(
                USER,
                {"account", "activities:upload"},
                state,
                MagicMock(),
                kind=None,
                status=None,
                cursor=None,
                num_records=10,
            )

        assert page.items == []

    def test_only_the_callers_own_jobs_are_listed(self, state):
        _strava(state, user_id=OTHER_USER)

        page = jobs_service.list_jobs(
            USER, {"account"}, state, MagicMock(), kind=None, status=None, cursor=None, num_records=10
        )

        assert page.items == []

    def test_a_kind_without_its_scope_is_not_listed_and_ingestion_is_not_asked(self, state):
        _strava(state)
        with patch(_INGESTION_LIST) as ingestion:
            page = jobs_service.list_jobs(
                USER, {"activities:read"}, state, MagicMock(), kind=None, status=None, cursor=None, num_records=10
            )

        assert page.items == []
        ingestion.assert_not_called()

    def test_kind_and_status_filter_the_list(self, state):
        gear = _strava(state)
        _strava(state, kind=strava_constants.SyncKind.LINK)
        strava_sync_state_store.StravaSyncStateStore(state).set_status(
            USER, strava_constants.SyncKind.LINK, Status.SUCCEEDED
        )
        with patch(_INGESTION_LIST) as ingestion:
            by_kind = jobs_service.list_jobs(
                USER,
                _ALL,
                state,
                MagicMock(),
                kind=jobs_schema.JobKind.STRAVA_GEAR,
                status=None,
                cursor=None,
                num_records=10,
            )
            by_status = jobs_service.list_jobs(
                USER, {"account"}, state, MagicMock(), kind=None, status=Status.QUEUED, cursor=None, num_records=10
            )

        assert [job.id for job in by_kind.items] == [gear.id]
        assert [job.id for job in by_status.items] == [gear.id]
        ingestion.assert_not_called()

    def test_ingestion_is_asked_for_the_listed_ingestion_kinds_and_status(self, state):
        db = MagicMock()
        with patch(_INGESTION_LIST, return_value=[]) as ingestion:
            jobs_service.list_jobs(
                USER,
                _ALL,
                state,
                db,
                kind=jobs_schema.JobKind.ACTIVITY_REFRESH,
                status=Status.RUNNING,
                cursor=None,
                num_records=5,
            )

        assert ingestion.call_args.args == (USER, db)
        assert ingestion.call_args.kwargs == {
            "kinds": {jobs_schema.JobKind.ACTIVITY_REFRESH},
            "status": Status.RUNNING,
            "before": None,
            "limit": 6,
        }


def test_every_kind_has_a_rule_and_a_status_model():
    union, _ = typing.get_args(jobs_schema.JobRead)
    union_kinds = set()
    for model in typing.get_args(union):
        union_kinds.update(typing.get_args(model.model_fields["kind"].annotation))

    assert union_kinds == {kind.value for kind in jobs_schema.JobKind}
    assert set(jobs_service._RULES) == set(jobs_schema.JobKind)
