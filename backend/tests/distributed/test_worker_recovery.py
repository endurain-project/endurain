"""What happens to an in-flight job when its worker dies, and when it merely runs long.

JASIL leases a claimed job to one worker. A worker that stops heartbeating loses
the lease and another worker takes the job over; a worker that keeps heartbeating
keeps it however long the handler runs. Both are about the whole deployment, so
both need real processes and a real clock: the lease is 60 seconds.
"""

from tests.distributed.cluster import LEASE_SECONDS

_UPLOAD_SUBSCRIBER = "activity_ingestion.uploaded_file"


def _upload_attempts(cluster) -> list[tuple[str, str]]:
    """``(outcome, worker)`` for each attempt at the upload job, oldest first."""
    return cluster.query(
        "SELECT a.outcome, a.worker_id FROM job_attempts a JOIN processing_jobs p ON p.id = a.job_id "
        "WHERE p.subscriber_id = :subscriber ORDER BY a.claimed_at",
        subscriber=_UPLOAD_SUBSCRIBER,
    )


def _slow_start_logged(cluster, worker) -> bool:
    return "SLOW-START" in cluster.log(worker)


def test_a_job_whose_worker_is_killed_is_finished_by_another_worker(cluster):
    cluster.start_api(distributed=True)
    doomed = cluster.start_worker(distributed=True, slow_seconds=600)
    (job_id,) = cluster.accept_uploads(1, "crash", distributed=True)
    assert cluster.wait_for(lambda: _slow_start_logged(cluster, doomed), 60), "the worker never claimed the upload"
    assert cluster.job_status(job_id) == "processing"

    cluster.kill(doomed)
    cluster.start_worker(distributed=True)

    # The lease has to expire and the reaper (every 60 s) has to notice before the survivor can claim it.
    assert cluster.wait_for_uploads([job_id], timeout=LEASE_SECONDS * 4)
    assert cluster.job_status(job_id) == "completed"

    attempts = _upload_attempts(cluster)
    assert [outcome for outcome, _worker in attempts] == ["lease_expired", "completed"]
    assert len({worker for _outcome, worker in attempts}) == 2, "the survivor, not the dead worker, finished it"
    assert cluster.scalar("SELECT count(*) FROM activities") == 1, "the import ran once, not twice"
    assert cluster.wait_for_durable_jobs(4), "the upload job and its three activity.created subscribers completed"


def test_a_handler_that_outlives_its_lease_is_not_taken_over(cluster):
    """The heartbeat renews the lease, so a slow import is neither requeued nor run twice."""
    cluster.start_api(distributed=True)
    slow = cluster.start_worker(distributed=True, slow_seconds=LEASE_SECONDS * 2.5)
    (job_id,) = cluster.accept_uploads(1, "slow", distributed=True)
    assert cluster.wait_for(lambda: _slow_start_logged(cluster, slow), 60)
    # Only now, so it cannot win the claim: it is idle and would take the job if its lease expired.
    cluster.start_worker(distributed=True)

    assert cluster.wait_for_uploads([job_id], timeout=LEASE_SECONDS * 5)

    assert cluster.job_status(job_id) == "completed"
    attempts = _upload_attempts(cluster)
    assert [outcome for outcome, _worker in attempts] == ["completed"], attempts
    assert cluster.scalar("SELECT count(*) FROM activities") == 1
