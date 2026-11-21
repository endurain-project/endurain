"""A user holds at most ten open uploads; the limit is enforced on the real route, even under concurrent requests.

The durable profile keeps every accepted upload pending, so a request count is a job count.
"""

import threading
import uuid

import pytest

import core.config as core_config
import modules.activities.activity_ingestion.constants as ingestion_constants
import modules.activities.activity_ingestion.crud as ingestion_crud
from tests._factories.garmin import activity_gpx
from tests._factories.ingestion import all_jobs, stage_job, staged_keys
from tests._factories.users import make_user

_API = core_config.ROOT_PATH
_CAP = ingestion_constants.MAX_OPEN_UPLOADS_PER_USER
_Kind = ingestion_constants.IngestionJobKind


@pytest.fixture
def me(make_signed_in):
    """A signed-in regular user."""
    return make_signed_in()


def _upload(user, key: str | None = None):
    headers = {"Idempotency-Key": f'"{key}"'} if key else {}
    return user.client.post(f"{_API}/activities/upload", files={"file": ("ride.gpx", activity_gpx())}, headers=headers)


def _fill(committed_sessions, user, count: int, **options) -> None:
    with committed_sessions() as db:
        for _ in range(count):
            stage_job(db, user.user.id, staged_key=f"{uuid.uuid4().hex}.gpx", **options)
        db.commit()


class TestTheRoute:
    @pytest.fixture(autouse=True)
    def _durable(self, durable_jobs):
        """Nothing runs the jobs, so the open ones stay open."""

    def test_refuses_the_upload_past_the_cap_before_storing_it(self, me, committed_sessions, storage):
        _fill(committed_sessions, me, _CAP)
        before = len(staged_keys(storage))

        response = _upload(me)

        assert response.status_code == 409
        assert "job_id" not in response.json()
        assert len(all_jobs(committed_sessions)) == _CAP
        assert len(staged_keys(storage)) == before

    def test_a_new_key_at_the_cap_is_refused_before_the_file_is_stored(self, me, committed_sessions, storage):
        _fill(committed_sessions, me, _CAP)

        response = _upload(me, "new-key")

        assert response.status_code == 409
        assert staged_keys(storage) == []

    def test_a_retry_with_the_same_key_is_replayed_even_at_the_cap(self, me, committed_sessions):
        first = _upload(me, "retry")
        _fill(committed_sessions, me, _CAP - 1)

        replay = _upload(me, "retry")

        assert replay.status_code == 202
        assert replay.json()["id"] == first.json()["id"]

    def test_the_last_free_slot_is_taken_by_the_next_upload(self, me, committed_sessions):
        _fill(committed_sessions, me, _CAP - 1)

        response = _upload(me)

        assert response.status_code == 202
        assert len(all_jobs(committed_sessions)) == _CAP

    def test_another_users_open_uploads_do_not_count(self, me, make_signed_in, committed_sessions):
        other = make_signed_in()
        _fill(committed_sessions, other, _CAP)

        assert _upload(me).status_code == 202

    def test_a_finished_upload_frees_its_slot(self, me, committed_sessions):
        _fill(committed_sessions, me, _CAP - 1)
        _fill(committed_sessions, me, 3, status="completed")
        _fill(committed_sessions, me, 3, status="failed")

        assert _upload(me).status_code == 202
        assert _upload(me).status_code == 409

    def test_two_uploads_racing_for_the_last_slot_admit_only_one(self, me, committed_sessions):
        _fill(committed_sessions, me, _CAP - 1)

        responses = _race(me, 2)

        assert sorted(response.status_code for response in responses) == [202, 409]
        assert len(all_jobs(committed_sessions)) == _CAP

    def test_a_burst_from_one_user_never_exceeds_the_cap(self, me, committed_sessions):
        responses = _race(me, _CAP + 5)

        statuses = sorted(response.status_code for response in responses)
        assert statuses == [202] * _CAP + [409] * 5
        assert len(all_jobs(committed_sessions)) == _CAP


def _race(user, count: int) -> list:
    barrier = threading.Barrier(count)
    responses: list = []

    def send() -> None:
        barrier.wait()
        responses.append(_upload(user))

    threads = [threading.Thread(target=send) for _ in range(count)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=60)
    return responses


class TestWhatCountsAsOpen:
    def _count(self, db, user_id) -> int:
        return ingestion_crud.count_open_uploads(user_id, db)

    def test_pending_processing_and_deferred_uploads_count(self, db):
        user = make_user(db)
        for status in ("pending", "processing", "deferred"):
            stage_job(db, user.id, status=status)

        assert self._count(db, user.id) == 3

    def test_finished_uploads_do_not(self, db):
        user = make_user(db)
        stage_job(db, user.id)
        stage_job(db, user.id, status="completed")
        stage_job(db, user.id, status="failed")

        assert self._count(db, user.id) == 1

    def test_other_kinds_and_other_users_do_not(self, db):
        user, other = make_user(db), make_user(db)
        stage_job(db, user.id, kind=_Kind.REFRESH)
        stage_job(db, user.id, kind=_Kind.BULK_IMPORT, import_source="generic", files_total=1)
        stage_job(db, other.id)

        assert self._count(db, user.id) == 0
