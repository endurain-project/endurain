"""Finding and listing background jobs across the features that own them, on the real database and state."""

import typing
import uuid
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta

import pytest
from jasil.backends.state_memory import MemoryState

import core.attempt_state as core_attempt_state
import core.exceptions as core_exceptions
import core.job_status as core_job_status
import modules.garmin.link_state_store as garmin_link_state_store
import modules.jobs.schema as jobs_schema
import modules.jobs.service as jobs_service
import modules.strava.constants as strava_constants
import modules.strava.sync_state_store as strava_sync_state_store
import modules.users.users.constants as users_constants
import modules.users.users.deletion_state_store as deletion_state_store
from tests._factories.jobs import make_ingestion_job_at
from tests._factories.users import make_user

OTHER_USER = uuid.UUID("7b1c93e4-5d28-4f6a-8e03-a94d2c6f1b57")
THIRD_USER = uuid.UUID("c3a85f19-0e72-4b4d-b6a8-3d9e17f4c250")
MISSING_JOB = uuid.UUID("a1000000-0000-4000-8000-000000000004")
ODD_JOB = uuid.UUID("a1000000-0000-4000-8000-000000000005")

Status = core_job_status.JobState
_ALL = frozenset(
    {"gears:write", "activities:write", "account", "account:integrations", "activities:upload", "users:read-all"}
)


class _NeverScanned(MemoryState):
    """A state backend that fails the test when the whole keyspace is scanned."""

    def iter_keys(self, prefix: str) -> Iterator[str]:
        """Fail: a listing must read the owner's index, not every key."""
        raise AssertionError("the keyspace was scanned")


@pytest.fixture
def state():
    return MemoryState()


@pytest.fixture
def user(db):
    created = make_user(db)
    db.flush()
    return created.id


def _at(monkeypatch, moment: datetime) -> None:
    """Make the state stores stamp the jobs they begin with ``moment``."""

    class _Moment(datetime):
        @classmethod
        def now(cls, tz=None):
            return moment

    monkeypatch.setattr(core_attempt_state, "datetime", _Moment)


def _strava(state, user_id, kind=strava_constants.SyncKind.GEAR):
    """Begin a Strava sync job as the route does."""
    return strava_sync_state_store.StravaSyncStateStore(state).begin(user_id, kind, conflict="Busy")


class TestGetJob:
    def test_the_owner_reads_a_state_store_job_with_its_rule(self, db, state, user):
        job = _strava(state, user)

        view = jobs_service.get_job(job.id, user, _ALL, state, db)

        assert view.job.id == job.id
        assert view.job.kind == "strava_gear"
        assert view.job.status == Status.QUEUED
        assert view.scope == "gears:write"
        assert view.poll_seconds == strava_constants.SYNC_POLL_SECONDS[strava_constants.SyncKind.GEAR]

    @pytest.mark.parametrize("kind", [strava_constants.SyncKind.LINK, strava_constants.SyncKind.UNLINK])
    def test_a_strava_link_or_unlink_job_is_read_with_the_integrations_scope(self, db, state, user, kind):
        job = _strava(state, user, kind)

        assert jobs_service.get_job(job.id, user, _ALL, state, db).scope == "account:integrations"

    def test_a_garmin_link_job_is_read_with_the_integrations_scope(self, db, state, user):
        job = garmin_link_state_store.GarminLinkStateStore(state).begin(user, conflict="Busy")

        assert jobs_service.get_job(job.id, user, _ALL, state, db).scope == "account:integrations"

    def test_another_users_job_is_not_found(self, db, state, user):
        job = _strava(state, OTHER_USER)

        with pytest.raises(core_exceptions.NotFoundError):
            jobs_service.get_job(job.id, user, _ALL, state, db)

    def test_a_job_its_subject_has_replaced_is_not_found(self, db, state, user):
        first = _strava(state, user)
        strava_sync_state_store.StravaSyncStateStore(state).set_status(
            user, strava_constants.SyncKind.GEAR, Status.SUCCEEDED, job_id=first.id
        )
        _strava(state, user)

        with pytest.raises(core_exceptions.NotFoundError):
            jobs_service.get_job(first.id, user, _ALL, state, db)

    def test_an_id_the_index_does_not_hold_is_read_as_an_ingestion_job(self, db, state, user):
        upload = make_ingestion_job_at(db, user, datetime(2026, 1, 1, tzinfo=UTC))

        view = jobs_service.get_job(upload.id, user, _ALL, state, db)

        assert view.job.id == upload.id
        assert view.scope == "activities:upload"

    def test_another_users_ingestion_job_is_not_found(self, db, state, user):
        upload = make_ingestion_job_at(db, user, datetime(2026, 1, 1, tzinfo=UTC))

        with pytest.raises(core_exceptions.NotFoundError):
            jobs_service.get_job(upload.id, OTHER_USER, _ALL, state, db)

    def test_an_unknown_id_is_not_found(self, db, state, user):
        with pytest.raises(core_exceptions.NotFoundError):
            jobs_service.get_job(MISSING_JOB, user, _ALL, state, db)

    def test_an_indexed_job_of_a_kind_no_feature_reads_is_not_found(self, db, state, user):
        core_attempt_state.JobIndex(state).put(
            core_job_status.JobRef(
                id=ODD_JOB, kind="retired_kind", owner_id=user, subject=str(user), created_at=datetime.now(UTC)
            ),
            60,
        )

        with pytest.raises(core_exceptions.NotFoundError):
            jobs_service.get_job(ODD_JOB, user, _ALL, state, db)

    def test_any_holder_of_users_read_all_follows_an_account_deletion(self, db, state, user):
        job = deletion_state_store.UserDeletionStateStore(state).begin(
            THIRD_USER, users_constants.DeletionKind.ACCOUNT, conflict="Busy", owner_id=user
        )

        view = jobs_service.get_job(job.id, OTHER_USER, {"users:read-all"}, state, db)

        assert view.job.kind == "user_deletion"
        with pytest.raises(core_exceptions.NotFoundError):
            jobs_service.get_job(job.id, OTHER_USER, {"gears:write"}, state, db)


def _list(db, state, user, scopes=_ALL, *, kind=None, status=None, cursor=None, num_records=10):
    return jobs_service.list_jobs(
        user, scopes, state, db, kind=kind, status=status, cursor=cursor, num_records=num_records
    )


class TestListJobs:
    def test_state_store_and_ingestion_jobs_are_merged_newest_first_and_paged(self, db, state, user, monkeypatch):
        jan10 = datetime(2026, 1, 10, 12, 0, tzinfo=UTC)
        _at(monkeypatch, jan10)
        gear = _strava(state, user)
        _at(monkeypatch, jan10 + timedelta(minutes=5))
        link = _strava(state, user, strava_constants.SyncKind.LINK)
        old = make_ingestion_job_at(db, user, jan10 - timedelta(days=1))
        new = make_ingestion_job_at(db, user, jan10 + timedelta(days=1))

        first = _list(db, state, user, num_records=2)

        assert [job.id for job in first.items] == [new.id, link.id]
        assert first.next_cursor is not None

        second = _list(db, state, user, cursor=first.next_cursor, num_records=2)

        assert [job.id for job in second.items] == [gear.id, old.id]
        assert second.next_cursor is None

    def test_the_state_store_is_listed_from_the_owner_index_without_scanning_the_keyspace(self, db, user, monkeypatch):
        state = _NeverScanned()
        _at(monkeypatch, datetime(2026, 1, 10, 12, 0, tzinfo=UTC))
        first = _strava(state, user)
        _at(monkeypatch, datetime(2026, 1, 10, 12, 5, tzinfo=UTC))
        second = _strava(state, user, strava_constants.SyncKind.LINK)

        page = _list(db, state, user)

        assert [job.id for job in page.items] == [second.id, first.id]

    def test_jobs_created_at_the_same_instant_are_paged_without_a_skip_or_repeat(self, db, state, user, monkeypatch):
        _at(monkeypatch, datetime(2026, 1, 10, 12, 0, tzinfo=UTC))
        created = [_strava(state, user, kind) for kind in strava_constants.SyncKind]
        expected = [job.id for job in sorted(created, key=lambda job: job.id, reverse=True)]

        seen: list[uuid.UUID] = []
        cursor = None
        while True:
            page = _list(db, state, user, cursor=cursor, num_records=1)
            seen.extend(job.id for job in page.items)
            cursor = page.next_cursor
            if cursor is None:
                break

        assert seen == expected

    def test_a_filter_that_drops_most_of_the_index_still_fills_the_page(self, db, state, user, monkeypatch):
        start = datetime(2026, 1, 10, 12, 0, tzinfo=UTC)
        _at(monkeypatch, start)
        gear = _strava(state, user)
        for minute in range(1, 8):
            _at(monkeypatch, start + timedelta(minutes=minute))
            link = _strava(state, user, strava_constants.SyncKind.LINK)
            strava_sync_state_store.StravaSyncStateStore(state).set_status(
                user, strava_constants.SyncKind.LINK, Status.SUCCEEDED, job_id=link.id
            )
            if minute < 7:
                state.delete(core_attempt_state.key("jobs", "ref", str(link.id)))

        page = _list(db, state, user, status=Status.QUEUED, num_records=1)

        assert [job.id for job in page.items] == [gear.id]

    def test_a_link_job_is_not_listed_without_the_integrations_scope(self, db, state, user):
        _strava(state, user, strava_constants.SyncKind.LINK)

        assert _list(db, state, user, {"gears:write", "activities:upload"}).items == []

    def test_only_the_callers_own_jobs_are_listed(self, db, state, user):
        other = make_user(db)
        db.flush()
        _strava(state, other.id)
        make_ingestion_job_at(db, other.id, datetime(2026, 1, 1, tzinfo=UTC))

        assert _list(db, state, user).items == []

    def test_a_kind_without_its_scope_is_not_listed(self, db, state, user):
        _strava(state, user)
        make_ingestion_job_at(db, user, datetime(2026, 1, 1, tzinfo=UTC))

        assert _list(db, state, user, {"activities:read"}).items == []

    def test_kind_and_status_filter_the_list(self, db, state, user):
        gear = _strava(state, user)
        link = _strava(state, user, strava_constants.SyncKind.LINK)
        strava_sync_state_store.StravaSyncStateStore(state).set_status(
            user, strava_constants.SyncKind.LINK, Status.SUCCEEDED, job_id=link.id
        )
        upload = make_ingestion_job_at(db, user, datetime(2026, 1, 1, tzinfo=UTC))

        by_kind = _list(db, state, user, kind=jobs_schema.JobKind.STRAVA_GEAR)
        by_status = _list(db, state, user, status=Status.SUCCEEDED)
        uploads = _list(db, state, user, kind=jobs_schema.JobKind.ACTIVITY_UPLOAD)
        refreshes = _list(db, state, user, kind=jobs_schema.JobKind.ACTIVITY_REFRESH)

        assert [job.id for job in by_kind.items] == [gear.id]
        assert [job.id for job in by_status.items] == [link.id]
        assert [job.id for job in uploads.items] == [upload.id]
        assert refreshes.items == []

    def test_an_ingestion_job_is_listed_by_its_status(self, db, state, user):
        upload = make_ingestion_job_at(db, user, datetime(2026, 1, 1, tzinfo=UTC))

        assert [job.id for job in _list(db, state, user, status=upload.status).items] == [upload.id]
        assert _list(db, state, user, status=Status.RUNNING).items == []

    def test_a_cursor_this_server_did_not_issue_is_refused(self, db, state, user):
        with pytest.raises(core_exceptions.InvalidInputError):
            _list(db, state, user, cursor="not-a-cursor")


def test_every_kind_has_a_rule_and_a_status_model():
    union, _ = typing.get_args(jobs_schema.JobRead)
    union_kinds = set()
    for model in typing.get_args(union):
        union_kinds.update(typing.get_args(model.model_fields["kind"].annotation))

    assert union_kinds == {kind.value for kind in jobs_schema.JobKind}
    assert set(jobs_service._RULES) == set(jobs_schema.JobKind)
