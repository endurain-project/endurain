import contextvars
import threading

import pytest

import core.exceptions as core_exceptions
import core.local_pool as core_local_pool


@pytest.fixture
def pool():
    pool = core_local_pool.BoundedPool("test-pool", workers=1, max_pending=2)
    yield pool
    pool.shutdown(wait=True)


def _blocked_job(started: threading.Event, release: threading.Event):
    def run() -> None:
        started.set()
        release.wait(timeout=5)

    return run


def test_runs_a_job_and_returns_its_result(pool):
    assert pool.submit(lambda value: value * 2, 21).result(timeout=5) == 42


def test_refuses_a_job_past_the_bound_and_takes_it_again_when_one_finishes(pool):
    started, release = threading.Event(), threading.Event()
    first = pool.submit(_blocked_job(started, release))
    started.wait(timeout=5)
    second = pool.submit(lambda: None)

    assert not pool.has_capacity()
    with pytest.raises(core_local_pool.PoolFullError) as full:
        pool.submit(lambda: None)
    assert isinstance(full.value, core_exceptions.ServiceUnavailableError)

    release.set()
    first.result(timeout=5)
    second.result(timeout=5)
    assert pool.has_capacity()
    assert pool.submit(lambda: "ok").result(timeout=5) == "ok"


def test_require_capacity_refuses_a_full_pool_without_taking_a_slot(pool):
    started, release = threading.Event(), threading.Event()
    pool.submit(_blocked_job(started, release))
    started.wait(timeout=5)
    pool.require_capacity()
    pool.submit(lambda: None)

    with pytest.raises(core_local_pool.PoolFullError):
        pool.require_capacity()
    release.set()


def test_waits_for_a_slot_when_asked_to(pool):
    started, release = threading.Event(), threading.Event()
    pool.submit(_blocked_job(started, release))
    started.wait(timeout=5)
    pool.submit(lambda: None)
    timer = threading.Timer(0.2, release.set)
    timer.start()

    assert pool.submit(lambda: "late", wait_seconds=5).result(timeout=5) == "late"


def test_a_failing_job_frees_its_slot(pool):
    def boom() -> None:
        raise RuntimeError("nope")

    future = pool.submit(boom)
    with pytest.raises(RuntimeError):
        future.result(timeout=5)

    assert pool.submit(lambda: 1).result(timeout=5) == 1
    assert pool.has_capacity()


def test_starts_again_after_a_shutdown(pool):
    pool.submit(lambda: None).result(timeout=5)
    pool.shutdown(wait=True)

    assert pool.submit(lambda: "restarted").result(timeout=5) == "restarted"


def test_jobs_run_under_the_submitters_context(pool):
    var = contextvars.ContextVar("request_id", default="none")
    var.set("req-1")

    assert pool.submit(var.get).result(timeout=5) == "req-1"
