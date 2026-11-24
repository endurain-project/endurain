"""API replicas started together on an empty database all come up: one migrates while the others wait."""

import httpx2


def test_replicas_starting_together_on_an_empty_database_all_start_and_answer(cluster):
    """The waiting replicas must not block the migrating one's concurrent index builds (a deadlock killed it)."""
    replicas = cluster.start_apis(3, distributed=True)

    for replica in replicas:
        assert httpx2.get(f"http://127.0.0.1:{replica.port}/api/v1/health", timeout=10).status_code == 200
