"""Uploads accepted by API replicas are imported by separate worker processes.

An API replica stages the file and queues the import through the transactional
outbox; the replica's relay turns the event into a durable job; a worker in another
process claims it, imports the file and fans out ``activity.created`` to its
subscribers. Nothing here is mocked: the processes only share PostgreSQL, Redis and
storage.
"""

from tests.distributed.cluster import STARTUP_SUBSCRIBERS

_GEOCODING_SUBSCRIBER = "activity_geocoding.reverse_geocode"
_DERIVED_SUBSCRIBERS = {
    _GEOCODING_SUBSCRIBER,
    "activity.notify_created",
    "activity_thumbnail.generate",
}
#: The derived work a dedicated enrichment worker takes.
_ENRICHMENT_SUBSCRIBERS = {_GEOCODING_SUBSCRIBER, "activity_thumbnail.generate"}


def _assert_everything_completed_exactly_once(cluster, job_ids, *, workers: int) -> None:
    assert cluster.wait_for_uploads(job_ids), {job: cluster.job_status(job) for job in job_ids}
    assert {cluster.job_status(job) for job in job_ids} == {"completed"}
    assert cluster.scalar("SELECT count(*) FROM activities") == len(job_ids), "one activity per upload"

    assert cluster.wait_for_durable_jobs(len(job_ids) * (1 + len(_DERIVED_SUBSCRIBERS))), cluster.query(
        "SELECT subscriber_id, status FROM jasil_processing_jobs"
    )
    per_subscriber = dict(
        cluster.query(
            "SELECT subscriber_id, count(*) FROM jasil_processing_jobs WHERE subscriber_id <> ALL(:startup) GROUP BY 1",
            startup=STARTUP_SUBSCRIBERS,
        )
    )
    assert per_subscriber.pop("activity_ingestion.uploaded_file") == len(job_ids)
    assert per_subscriber == dict.fromkeys(_DERIVED_SUBSCRIBERS, len(job_ids))

    outcomes = cluster.query(
        "SELECT p.subscriber_id, a.outcome, count(*) FROM jasil_job_attempts a "
        "JOIN jasil_processing_jobs p ON p.id = a.job_id GROUP BY 1, 2"
    )
    # A lookup whose geocoding turn is not free yet defers to the turn it booked (one lookup a second), so several
    # uploads at once defer some geocoding jobs; anything else that does not complete is a retry, reclaim or
    # supersession.
    unexpected = [
        row for row in outcomes if row[1] != "completed" and (row[0], row[1]) != (_GEOCODING_SUBSCRIBER, "deferred")
    ]
    assert not unexpected, f"no retries, reclaims or supersessions expected: {outcomes}"
    assert not cluster.query(
        "SELECT job_id FROM jasil_job_attempts WHERE outcome = 'completed' GROUP BY 1 HAVING count(*) > 1"
    ), "no job ran twice"

    # The cluster's processes call its loopback stand-ins, never the public OpenStreetMap services: every activity
    # was located by the geocoding stand-in, and the thumbnails were rendered from the tile stand-in.
    assert cluster.scalar("SELECT count(*) FROM activities WHERE city = 'Lisbon'") == len(job_ids)
    assert len(cluster.geocoder.requests) >= len(job_ids)
    assert cluster.tiles.requests, "thumbnails fetched tiles from the stand-in"

    registered = cluster.query(
        "SELECT stopped_at IS NULL, now() - last_heartbeat_at < interval '30 seconds' FROM jasil_job_workers"
    )
    assert registered == [(True, True)] * workers, "every worker registered with a live heartbeat"
    assert cluster.error_lines() == []


def test_a_standalone_worker_imports_what_the_api_queued(cluster):
    """Local profile: the API only publishes and relays; a dedicated worker consumes."""
    cluster.start_api(distributed=False)
    cluster.start_worker(distributed=False)

    job_ids = cluster.accept_uploads(4, "local", distributed=False)

    _assert_everything_completed_exactly_once(cluster, job_ids, workers=1)


def test_two_replicas_and_two_workers_share_one_deployment(cluster):
    """Distributed profile: Redis state and events, S3 storage, replicas and workers that never share a disk."""
    cluster.start_api(distributed=True)
    cluster.start_api(distributed=True)
    cluster.start_worker(distributed=True)
    cluster.start_worker(distributed=True)

    job_ids = cluster.accept_uploads(4, "replica-a", distributed=True)
    job_ids += cluster.accept_uploads(4, "replica-b", distributed=True)

    _assert_everything_completed_exactly_once(cluster, job_ids, workers=2)


def test_a_default_queue_worker_imports_while_enrichment_waits_for_its_own_worker(cluster):
    """Uploads and their notifications never queue behind thumbnails and geocoding: those wait for their own worker."""
    cluster.start_api(distributed=False)
    cluster.start_worker(distributed=False, queues="default")

    job_ids = cluster.accept_uploads(3, "queues", distributed=False)

    assert cluster.wait_for_uploads(job_ids), {job: cluster.job_status(job) for job in job_ids}
    assert cluster.wait_for(
        lambda: (
            cluster.scalar(
                "SELECT count(*) FROM jasil_processing_jobs WHERE subscriber_id = 'activity.notify_created' "
                "AND status = 'completed'"
            )
            == len(job_ids)
        ),
        60,
    )
    waiting = cluster.query(
        "SELECT subscriber_id, queue, status, attempts FROM jasil_processing_jobs WHERE subscriber_id = ANY(:ids)",
        ids=sorted(_ENRICHMENT_SUBSCRIBERS),
    )
    assert sorted(waiting) == sorted(
        (subscriber, "enrichment", "pending", 0) for subscriber in _ENRICHMENT_SUBSCRIBERS for _ in job_ids
    )

    cluster.start_worker(distributed=False, queues="enrichment")

    _assert_everything_completed_exactly_once(cluster, job_ids, workers=2)
