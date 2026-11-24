"""An ``Idempotency-Key`` is honoured across API replicas: of two simultaneous creates one runs and one is refused.

The replicas share only PostgreSQL and Redis. Each is a separate process that mounts the real health-poop route behind
the idempotency middleware, so the claim and the stored result travel through Redis, not through memory.
"""

import json
import subprocess
import sys
import time

from tests.distributed.cluster import _APP_DIR, _SUPPORT_DIR

_KEY = '"distributed-0001"'


def _driver(cluster, *args: str) -> subprocess.Popen:
    return subprocess.Popen(  # noqa: S603 - fixed argv built from this repo's own entry points
        [sys.executable, str(_SUPPORT_DIR / "idempotent_create.py"), *args],
        cwd=_APP_DIR,
        env=cluster.env(distributed=True),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )


def _result(process: subprocess.Popen) -> tuple[int, str, str]:
    out, err = process.communicate(timeout=180)
    line = next((line for line in out.splitlines() if line.startswith("RESULT ")), None)
    assert line is not None, f"the driver failed:\n{err[-2000:]}"
    status, rest = line.removeprefix("RESULT ").split(" ", 1)
    body, retry_after = rest.rsplit(" ", 1)
    return int(status), body, retry_after


def test_two_replicas_racing_on_one_key_create_one_record(cluster):
    cluster.start_api(distributed=True)
    seed = _driver(cluster, "seed")
    out, err = seed.communicate(timeout=120)
    user_id = next((line.removeprefix("USER ") for line in out.splitlines() if line.startswith("USER ")), None)
    assert user_id is not None, f"the seed failed:\n{err[-2000:]}"

    start_at = str(time.time() + 25)
    racers = [_driver(cluster, "post", user_id, _KEY, start_at) for _ in range(2)]
    outcomes = [_result(racer) for racer in racers]

    statuses = sorted(status for status, _body, _retry in outcomes)
    # The route lingers for seconds, so the second request arrives while the first still holds the claim.
    assert statuses == [201, 409], outcomes
    for status, body, retry_after in outcomes:
        if status == 409:
            assert json.loads(body)["type"] == "urn:endurain:error:idempotency-key-in-flight"
            assert int(retry_after) >= 1
    assert cluster.scalar("SELECT count(*) FROM health_poop") == 1

    status, body, _retry = _result(_driver(cluster, "post", user_id, _KEY, "0"))
    first = next(body for status, body, _retry in outcomes if status == 201)
    assert (status, body) == (201, first), "a repeat after both finished replays the stored response"
    assert cluster.scalar("SELECT count(*) FROM health_poop") == 1
    assert cluster.error_lines() == []
