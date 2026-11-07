"""A realtime hint reaches a websocket held by a different process than the one that published it.

A socket lives in one API replica's memory. The hint travels over the platform's realtime
channel (Redis pub/sub), so a process that holds no socket (the job worker, or another
replica) can still reach it. Nothing here is mocked: the processes share only Redis.
"""

import json
import subprocess
import sys
import time

from websockets.sync.client import connect

from tests.distributed.cluster import _APP_DIR, _SUPPORT_DIR

_USER_ID = 7


def _run(cluster, script: str, *args: str, distributed: bool = True) -> str:
    result = subprocess.run(  # noqa: S603 - fixed argv built from this repo's own entry points
        [sys.executable, str(_SUPPORT_DIR / script), *args],
        cwd=_APP_DIR,
        env=cluster.env(distributed=distributed),
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert result.returncode == 0, f"{script} failed:\n{result.stderr[-2000:]}"
    return result.stdout


def _connect(cluster, api):
    ticket = next(
        line.removeprefix("TICKET ")
        for line in _run(cluster, "mint_ticket.py", str(_USER_ID)).splitlines()
        if line.startswith("TICKET ")
    )
    return connect(f"ws://127.0.0.1:{api.port}/api/v1/ws?ticket={ticket}", open_timeout=15)


def _wait_until_held(cluster, api) -> None:
    """Let the replica register the connection before a hint is published."""
    time.sleep(1)


def test_a_process_without_sockets_reaches_a_socket_held_by_an_api_replica(cluster):
    """The worker case: the publisher holds no connection and never subscribes."""
    api = cluster.start_api(distributed=True)

    with _connect(cluster, api) as socket:
        _wait_until_held(cluster, api)
        _run(cluster, "push_hint.py", str(_USER_ID), "NEW_ACTIVITY_NOTIFICATION")

        message = json.loads(socket.recv(timeout=15))

    assert message == {"message": "NEW_ACTIVITY_NOTIFICATION", "notification_id": 1}
    assert cluster.error_lines() == []


def test_a_replica_that_does_not_hold_the_socket_does_not_swallow_the_hint(cluster):
    """Two replicas: the socket is on one, the hint is published while both are subscribed."""
    holder = cluster.start_api(distributed=True)
    cluster.start_api(distributed=True)

    with _connect(cluster, holder) as socket:
        _wait_until_held(cluster, holder)
        _run(cluster, "push_hint.py", str(_USER_ID), "NEW_FOLLOWER_REQUEST_NOTIFICATION")

        message = json.loads(socket.recv(timeout=15))

    assert message["message"] == "NEW_FOLLOWER_REQUEST_NOTIFICATION"
    assert cluster.error_lines() == []
