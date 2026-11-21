"""An ``Idempotency-Key`` on an upload makes a client's retry safe, through the real route and database.

The durable profile keeps every job pending (nothing runs it), so what a replay stores is visible: one job row and one
staged blob however often the request is repeated. The deleted-activity cases run on the local profile, where the job
finishes.
"""

import threading
import uuid

import pytest

import core.config as core_config
import modules.activities.activity_ingestion.constants as ingestion_constants
from tests._factories.garmin import EMPTY_GPX, activity_gpx
from tests._factories.ingestion import all_jobs, read_job, staged_keys

_API = core_config.ROOT_PATH
_UPLOAD = ingestion_constants.IngestionJobKind.UPLOAD


@pytest.fixture
def me(make_signed_in):
    """A signed-in regular user."""
    return make_signed_in()


def _upload(user, key: str | None, content: bytes | None = None, name: str = "ride.gpx"):
    headers = {"Idempotency-Key": f'"{key}"'} if key else {}
    return user.client.post(
        f"{_API}/activities/upload", files={"file": (name, content or activity_gpx())}, headers=headers
    )


def _delete_activity(user, activity_id: str) -> None:
    etag = user.client.get(f"{_API}/activities/{activity_id}").headers["ETag"]
    response = user.client.delete(f"{_API}/activities/{activity_id}", headers={"If-Match": etag})
    assert response.status_code == 204, response.text


class TestAReplayOnTheDurableProfile:
    @pytest.fixture(autouse=True)
    def _durable(self, durable_jobs):
        """Nothing runs the jobs, so a repeated request leaves a trace in the rows and the storage."""

    def test_returns_the_original_job_and_stores_nothing_again(self, me, committed_sessions, storage):
        first = _upload(me, "retry-1")
        replay = _upload(me, "retry-1")

        assert (first.status_code, replay.status_code) == (202, 202)
        assert replay.json()["id"] == first.json()["id"]
        assert replay.headers["Content-Location"] == first.headers["Content-Location"]
        assert len(all_jobs(committed_sessions)) == 1
        assert len(staged_keys(storage)) == 1

    def test_stores_the_key_and_the_fingerprint_of_what_was_sent(self, me, committed_sessions):
        response = _upload(me, "retry-2")

        row = read_job(committed_sessions, uuid.UUID(response.json()["id"]))
        assert row.idempotency_key == "retry-2"
        assert row.request_fingerprint is not None
        assert len(row.request_fingerprint) == 64

    def test_without_a_key_nothing_is_stored_on_the_job(self, me, committed_sessions):
        response = _upload(me, None)

        row = read_job(committed_sessions, uuid.UUID(response.json()["id"]))
        assert (row.idempotency_key, row.request_fingerprint) == (None, None)

    def test_is_scoped_to_the_caller(self, me, make_signed_in, committed_sessions):
        other = make_signed_in()
        mine = _upload(me, "shared-key")
        theirs = _upload(other, "shared-key")

        assert theirs.status_code == 202
        assert theirs.json()["id"] != mine.json()["id"]
        assert len(all_jobs(committed_sessions)) == 2

    def test_with_different_content_is_refused_and_stores_nothing(self, me, committed_sessions, storage):
        first = _upload(me, "retry-3")

        reused = _upload(me, "retry-3", activity_gpx(name="A different ride"))

        assert (first.status_code, reused.status_code) == (202, 422)
        assert reused.json()["type"].endswith("idempotency-key-reused")
        assert len(all_jobs(committed_sessions)) == 1
        assert len(staged_keys(storage)) == 1

    def test_requests_racing_with_one_key_end_in_one_job(self, me, committed_sessions, storage):
        barrier = threading.Barrier(4)
        responses: list = []

        def send() -> None:
            barrier.wait()
            responses.append(_upload(me, "race-1"))

        threads = [threading.Thread(target=send) for _ in range(4)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=30)

        assert sorted(response.status_code for response in responses) == [202] * 4
        assert len({response.json()["id"] for response in responses}) == 1
        assert len(all_jobs(committed_sessions)) == 1
        assert len(staged_keys(storage)) == 1

    def test_racing_with_one_key_and_different_content_admits_one_file(self, me, committed_sessions, storage):
        barrier = threading.Barrier(2)
        responses: list = []

        def send(content: bytes) -> None:
            barrier.wait()
            responses.append(_upload(me, "race-2", content))

        threads = [
            threading.Thread(target=send, args=(activity_gpx(name=name),)) for name in ("First ride", "Second ride")
        ]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=30)

        assert sorted(response.status_code for response in responses) == [202, 422]
        assert len(all_jobs(committed_sessions)) == 1
        assert len(staged_keys(storage)) == 1


class TestAKeyAfterTheImportFinished:
    def test_a_replay_of_a_surviving_activity_answers_with_the_finished_job(self, me, pool, committed_sessions):
        first = _upload(me, "done-1")
        pool.drain()

        replay = _upload(me, "done-1")

        assert replay.json()["id"] == first.json()["id"]
        assert replay.json()["status"] == "succeeded"
        assert len(all_jobs(committed_sessions)) == 1

    def test_the_key_is_released_once_every_activity_it_created_is_deleted(self, me, pool, committed_sessions):
        first = _upload(me, "done-2")
        pool.drain()
        (activity_id,) = me.client.get(f"{_API}/jobs/{first.json()['id']}").json()["activity_ids"]
        _delete_activity(me, activity_id)

        again = _upload(me, "done-2")
        pool.drain()

        assert again.status_code == 202
        assert again.json()["id"] != first.json()["id"]
        state = me.client.get(f"{_API}/jobs/{again.json()['id']}").json()
        assert state["status"] == "succeeded"
        assert state["activity_ids"] != [activity_id]
        assert read_job(committed_sessions, uuid.UUID(first.json()["id"])).idempotency_key is None

    def test_different_content_is_refused_instead_of_releasing_the_key(self, me, pool, committed_sessions):
        first = _upload(me, "done-3")
        pool.drain()
        (activity_id,) = me.client.get(f"{_API}/jobs/{first.json()['id']}").json()["activity_ids"]
        _delete_activity(me, activity_id)

        reused = _upload(me, "done-3", activity_gpx(name="Another ride"))

        assert reused.status_code == 422
        assert len(all_jobs(committed_sessions)) == 1

    def test_a_job_that_failed_keeps_its_key(self, me, pool, committed_sessions):
        first = _upload(me, "failed-1", EMPTY_GPX)
        pool.drain()

        replay = _upload(me, "failed-1", EMPTY_GPX)

        assert first.json()["id"] == replay.json()["id"]
        assert replay.json()["status"] == "failed"
