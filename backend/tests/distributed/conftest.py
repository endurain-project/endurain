"""Fixtures for the tests that run real API and worker processes.

They start ``uvicorn`` API replicas and ``worker.py`` job workers as separate OS
processes against disposable PostgreSQL, Redis and an S3-compatible store, which
is the only way to see what several processes do to one database: the outbox
relay turning events into jobs, workers competing for them, a worker dying
mid-job and a lease outliving its handler. They are slow (a few minutes) and
skipped unless every service below is configured, so the default ``pytest`` run
and CI need none of them.

    docker run -d --rm --name e-pg -e POSTGRES_USER=endurain -e POSTGRES_PASSWORD=test \\
        -e POSTGRES_DB=endurain_test -p 55432:5432 postgres:18
    docker run -d --rm --name e-redis -p 56379:6379 redis:7
    docker run -d --rm --name e-s3 -p 59090:9090 adobe/s3mock:latest
    TEST_DATABASE_URL=postgresql+psycopg://endurain:test@localhost:55432/endurain_test \\
    TEST_REDIS_URL=redis://localhost:56379/0 \\
    TEST_S3_ENDPOINT_URL=http://localhost:59090 \\
        uv run pytest -m distributed

The database named by ``TEST_DATABASE_URL`` must be disposable (its name must
contain ``test``); each test works in a database of its own beside it and drops
it afterwards. The Redis database is flushed and the S3 bucket emptied.
"""

import os

import pytest

from tests.distributed.cluster import Cluster, ClusterConfig

_REQUIRED = ("TEST_DATABASE_URL", "TEST_REDIS_URL", "TEST_S3_ENDPOINT_URL")


def pytest_collection_modifyitems(items):
    """Mark every test in this directory so ``-m distributed`` selects them."""
    for item in items:
        if "tests/distributed/" in str(item.fspath).replace("\\", "/"):
            item.add_marker(pytest.mark.distributed)


@pytest.fixture
def cluster(request, tmp_path):
    """Build a throwaway deployment; every process and database is torn down afterwards."""
    missing = [name for name in _REQUIRED if not os.environ.get(name)]
    if missing:
        pytest.skip(f"{', '.join(missing)} not set")
    config = ClusterConfig(
        database_url=os.environ["TEST_DATABASE_URL"],
        redis_url=os.environ["TEST_REDIS_URL"],
        s3_endpoint_url=os.environ["TEST_S3_ENDPOINT_URL"],
        s3_bucket=os.environ.get("TEST_S3_BUCKET", "endurain-test"),
    )
    deployment = Cluster(config, tmp_path, name=request.node.name)
    try:
        yield deployment
    finally:
        deployment.close()
