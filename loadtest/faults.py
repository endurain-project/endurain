"""Fault injection for the load-test stack: each scenario runs under a steady Locust load, then ``invariants.py`` runs.

Run through ``./run.sh faults`` (it brings the stack up and seeds it); by hand against a running stack::

    uv run python faults.py --run faults-manual [--only worker_kill,redis_outage]

Scenarios, in this order (the Strava one leaves the applications in their 15-minute back-off, so it is last):

* ``worker_kill``      SIGKILL the worker that holds jobs while an upload burst is in flight, start it again: every
                       job ends once (the lease expires, the reaper requeues it; no job runs twice).
* ``api_restart``      restart one API replica during load: requests in flight may fail, nothing is lost or duplicated.
* ``redis_outage``     stop Redis for 20 s: the documented degradation (``/health`` says ``degraded``, reads keep
                       working, WebSocket tickets answer 503) and a full recovery after.
* ``postgres_faults``  through toxiproxy: 200 ms latency, then every connection reset: no job stuck, no duplicate, the
                       pool recovers.
* ``strava_429``       the stub answers every Strava call with 429 for a burst: refreshes are deferred, not failed.

Every scenario writes its Locust files and ``invariants.json`` to ``results/<run>/<scenario>/`` and its outcome to
``results/<run>/faults.json``. A scenario fails when an invariant breaks, an assertion about the fault does not hold, or
the stack is not back within the scenario's recovery bound (stated in :data:`SCENARIOS`). Exit status is non-zero then.
"""

import argparse
import json
import os
import signal
import subprocess
import sys
import threading
import time
import uuid
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

import gpxgen
import invariants
import psycopg
import requests

HERE = Path(__file__).resolve().parent
HOST = os.environ.get("LOADTEST_HOST", "http://localhost:18080")
TOXIPROXY = os.environ.get("LOADTEST_TOXIPROXY", "http://localhost:18474")
STUB = os.environ.get("LOADTEST_STUB_ADMIN", "http://localhost:18081")
DATABASE_URL = invariants.database_url()
RESULTS = Path(os.environ.get("LOADTEST_RESULTS", HERE / "results"))
USERS_FILE = HERE / "data" / "users.json"
COMPOSE = ["docker", "compose", "-p", "endurain-load", "--env-file", ".env.loadtest", "-f", "compose.yaml"]

#: Virtual users of the background load, and the user classes (locustfile.py) that make it.
BACKGROUND_USERS = 16
BACKGROUND_CLASSES = ["AthleteUser", "UploaderUser", "StravaUser"]
#: Seconds of load before a fault, and after the stack is back, so recovery is shown under load.
WARM_UP = 20
SETTLE = 20
#: Seconds the invariants wait for the jobs and the outbox to drain once the load has stopped. A killed worker's jobs
#: wait for the lease (45 s) and the reaper (every minute), so this is the bound of "every job ends".
DRAIN_TIMEOUT = 240.0


@dataclass
class Scenario:
    """The outcome of one scenario."""

    name: str
    recovery_bound_s: float
    assertions: list[dict] = field(default_factory=list)
    notes: dict = field(default_factory=dict)
    recovered_in_s: float | None = None
    error: str | None = None

    def check(self, name: str, ok: bool, detail: str = "") -> bool:
        """Record an assertion about the fault and print it."""
        self.assertions.append({"assertion": name, "ok": ok, "detail": detail})
        print(f"  [{'ok' if ok else 'FAIL'}] {name}" + (f": {detail}" if detail else ""), flush=True)
        return ok


# ------------------------------------------------------------------------------------------------------------------
# The stack
# ------------------------------------------------------------------------------------------------------------------


def compose(*args: str, check: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run([*COMPOSE, *args], cwd=HERE, capture_output=True, text=True, check=check)


def docker(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["docker", *args], capture_output=True, text=True, check=True)


def container_ids(service: str) -> list[str]:
    """The ids of a service's containers, running or not, by container number."""
    ids = compose("ps", "-a", "-q", service).stdout.split()
    names = {i: docker("inspect", "-f", "{{.Name}}", i).stdout.strip() for i in ids}
    return sorted(ids, key=lambda i: names[i])


def db() -> psycopg.Connection:
    return psycopg.connect(DATABASE_URL, autocommit=True)


def db_now() -> datetime:
    """The database's clock: the Docker VM's clock may differ from this machine's, and the rows carry the former."""
    with db() as conn:
        return conn.execute("SELECT now()").fetchone()[0]


def health() -> dict | None:
    """``/api/v1/health`` through the proxy, or None when it does not answer 200."""
    try:
        resp = requests.get(f"{HOST}/api/v1/health", timeout=5)
        return resp.json() if resp.status_code == 200 else None
    except (requests.RequestException, ValueError):
        return None


def wait_for(condition: Callable[[], bool], bound: float, interval: float = 1.0) -> float | None:
    """Poll until the condition holds; return the seconds it took, or None when ``bound`` passed first."""
    started = time.monotonic()
    while time.monotonic() - started < bound:
        try:
            if condition():
                return time.monotonic() - started
        except (requests.RequestException, psycopg.Error, subprocess.CalledProcessError):
            pass
        time.sleep(interval)
    return None


def healthy() -> bool:
    body = health()
    return body is not None and body.get("status") == "ok"


def replicas_healthy(service: str, count: int) -> bool:
    """Whether ``count`` containers of a service run and, when the image has a healthcheck, pass it."""
    ids = container_ids(service)
    states = [
        docker(
            "inspect", "-f", "{{.State.Status}} {{if .State.Health}}{{.State.Health.Status}}{{end}}", i
        ).stdout.split()
        for i in ids
    ]
    return len(states) == count and all(s[0] == "running" and (len(s) == 1 or s[1] == "healthy") for s in states)


# ------------------------------------------------------------------------------------------------------------------
# Clients of the application (the fault scenarios' own traffic, beside the Locust load)
# ------------------------------------------------------------------------------------------------------------------


class Client:
    """A signed-in API client of one seeded account."""

    def __init__(self, seed: dict, account: dict, tag: int) -> None:
        self.account = account
        self.ip = f"10.200.{tag}.{uuid.uuid4().int % 200 + 2}"
        self.password = seed["password"]
        self.token = ""
        self.session = requests.Session()

    def headers(self) -> dict[str, str]:
        return {"X-LoadTest-Client-IP": self.ip, "Authorization": f"Bearer {self.token}"}

    def login(self) -> requests.Response:
        resp = self.session.post(
            f"{HOST}/api/v1/auth/login",
            data={"username": self.account["username"], "password": self.password},
            headers={"X-LoadTest-Client-IP": self.ip, "X-Client-Type": "web"},
            timeout=15,
        )
        if resp.status_code == 200 and resp.json().get("next_step") == "tokens":
            self.token = resp.json()["access_token"]
        return resp

    def get(self, path: str, **kwargs) -> requests.Response:
        return self.session.get(f"{HOST}/api/v1{path}", headers=self.headers(), timeout=15, **kwargs)

    def post(self, path: str, **kwargs) -> requests.Response:
        return self.session.post(
            f"{HOST}/api/v1{path}", headers={**self.headers(), **kwargs.pop("headers", {})}, timeout=30, **kwargs
        )


class Uploads:
    """An upload burst sent by the fault scenario itself, so the jobs it makes can be followed to the end.

    Each upload is recorded as the Locust ledger records its own (``uploads``), so ``invariants.py`` checks them with
    the rest: one job per key, one stored activity per succeeded job, no job left open.
    """

    def __init__(self, scenario: str, run_index: int, seed: dict, accounts: list[dict]) -> None:
        self.scenario = scenario
        self.run_index = run_index
        self.clients = [Client(seed, account, 100 + i) for i, account in enumerate(accounts)]
        self.entries: list[dict] = []
        self.sent = 0
        self.lost = 0
        self._lock = threading.Lock()

    def burst(self, per_account: int) -> None:
        """Log every account in and send ``per_account`` uploads from each at once (the server caps open ones at 10)."""
        for client in self.clients:
            client.login()
        with ThreadPoolExecutor(max_workers=len(self.clients) * per_account) as pool:
            for n, client in enumerate(self.clients):
                for k in range(per_account):
                    pool.submit(self._upload, client, 60 + n, self.sent_index(), k)

    def sent_index(self) -> int:
        with self._lock:
            self.sent += 1
            return self.sent

    def _upload(self, client: Client, vid: int, n: int, _k: int) -> None:
        key = f'"{uuid.uuid4()}"'
        name = f"load-{self.scenario}-f{vid}-{n}.gpx"
        data = gpxgen.gpx(vid, n, self.run_index)
        try:
            resp = client.post(
                "/activities/upload",
                files={"file": (name, data, "application/gpx+xml")},
                headers={"Idempotency-Key": key},
            )
        except requests.RequestException:
            with self._lock:
                self.lost += 1
            return
        if resp.status_code == 202:
            with self._lock:
                self.entries.append(
                    {
                        "job_id": resp.json()["id"],
                        "key": key,
                        "user_id": client.account["user_id"],
                        "status": "queued",
                        "activity_ids": [],
                        "bytes": len(data),
                    }
                )

    def settle(self, bound: float) -> float | None:
        """Wait until every accepted job has ended in the database; record the outcome on the entries."""

        def ended() -> bool:
            with db() as conn:
                rows = conn.execute(
                    "SELECT id::text, status, activity_ids FROM activity_ingestion_jobs WHERE id = ANY(%s::uuid[])",
                    ([e["job_id"] for e in self.entries],),
                ).fetchall()
            states = {job_id: (status, ids) for job_id, status, ids in rows}
            for entry in self.entries:
                status, ids = states.get(entry["job_id"], ("missing", []))
                entry["status"] = "succeeded" if status == "completed" else status
                entry["activity_ids"] = [str(i) for i in (ids or [])]
            return all(s[0] in ("completed", "failed") for s in states.values()) and len(states) == len(self.entries)

        return wait_for(ended, bound, interval=2.0) if self.entries else 0.0


# ------------------------------------------------------------------------------------------------------------------
# Background load
# ------------------------------------------------------------------------------------------------------------------


class Load:
    """A Locust process driving the steady background load, stopped with SIGTERM (SIGINT is ignored in a background job) so it writes its summary and ledger."""

    def __init__(self, run: str, scenario: str, run_index: int, burst: str = "") -> None:
        self.dir = RESULTS / run / scenario
        self.dir.mkdir(parents=True, exist_ok=True)
        env = {
            **os.environ,
            "LOADTEST_RUN": scenario,
            "LOADTEST_RESULTS": str(RESULTS / run),
            "LOADTEST_RUN_INDEX": str(run_index),
            "LOADTEST_USERS_FILE": str(USERS_FILE),
            "LOADTEST_STRAVA_BURST": burst,
        }
        self.proc = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "locust",
                "-f",
                str(HERE / "locustfile.py"),
                "--headless",
                "-u",
                str(BACKGROUND_USERS),
                "-r",
                "4",
                "-t",
                "1h",
                "--host",
                HOST,
                "--csv",
                str(self.dir / "locust"),
                "--exit-code-on-error",
                "0",
                "--stop-timeout",
                "30",
                "--only-summary",
                *BACKGROUND_CLASSES,
            ],
            cwd=HERE,
            env=env,
            stdout=(self.dir / "locust.out").open("w"),
            stderr=subprocess.STDOUT,
        )

    def stop(self) -> None:
        """Stop the load and wait for the summary and the ledger."""
        if self.proc.poll() is None:
            self.proc.send_signal(signal.SIGTERM)
        try:
            self.proc.wait(timeout=120)
        except subprocess.TimeoutExpired:
            self.proc.kill()
            self.proc.wait()

    def summary(self) -> dict:
        try:
            return json.loads((self.dir / "summary.json").read_text())
        except (FileNotFoundError, ValueError):
            return {}


# ------------------------------------------------------------------------------------------------------------------
# Scenarios
# ------------------------------------------------------------------------------------------------------------------


def worker_kill(sc: Scenario, ctx: "Context") -> None:
    """SIGKILL the only default-queue worker while it holds jobs of an upload burst; start a new one."""
    # One worker on the default queue, so the default-queue jobs the database shows claimed are known to be its (a
    # worker's id there is a random UUID, not the container's name; the background worker serves only its own queue).
    # The scale-down stops the second worker gracefully.
    compose("up", "-d", "--no-recreate", "--scale", "worker=1", "worker")
    victim = container_ids("worker")[0]
    uploads = ctx.uploads
    uploads.burst(per_account=8)
    sc.notes["uploads_sent"] = len(uploads.entries)

    def claimed() -> int:
        with db() as conn:
            return conn.execute(
                "SELECT count(*) FROM jasil_processing_jobs WHERE status = 'claimed' AND queue = 'default'"
            ).fetchone()[0]

    held = 0
    started = time.monotonic()
    while held == 0 and time.monotonic() - started < 30:
        held = claimed()
    sc.check("the worker held claimed jobs when it was killed", held > 0, f"{held} claimed jobs")
    docker("kill", "-s", "KILL", victim)
    killed_at = time.monotonic()
    # The attempts open at the kill are the dead worker's, whenever it claimed them (some during the warm-up load).
    with db() as conn:
        open_attempts = [
            row[0]
            for row in conn.execute("SELECT id FROM jasil_job_attempts WHERE outcome IS NULL AND queue = 'default'")
        ]
    sc.notes["jobs_claimed_at_the_kill"] = held
    sc.notes["attempts_open_at_the_kill"] = len(open_attempts)
    print(f"  killed the worker holding {held} claimed jobs", flush=True)
    compose("up", "-d", "--no-recreate", "--scale", "worker=2", "worker")
    ended = uploads.settle(sc.recovery_bound_s)
    sc.recovered_in_s = None if ended is None else time.monotonic() - killed_at
    sc.check(
        "every upload of the burst ended after the kill",
        ended is not None,
        f"{len(uploads.entries)} jobs ended {sc.recovered_in_s and round(sc.recovered_in_s)} s after the kill"
        if ended is not None
        else f"not all ended within {sc.recovery_bound_s:.0f} s",
    )
    states = [e["status"] for e in uploads.entries]
    sc.check(
        "none of them failed",
        "failed" not in states,
        f"{states.count('succeeded')} succeeded, {states.count('failed')} failed",
    )

    # The jobs the worker held (the uploads and their notifications) wait for their lease to run out and for the
    # reaper, so the fault is over when no durable job is open.
    def nothing_open() -> bool:
        with db() as conn:
            return (
                conn.execute(
                    "SELECT count(*) FROM jasil_processing_jobs WHERE status IN ('pending', 'claimed')"
                ).fetchone()[0]
                == 0
            )

    drained = wait_for(nothing_open, sc.recovery_bound_s, interval=2.0)
    sc.recovered_in_s = None if drained is None else time.monotonic() - killed_at
    sc.check(
        "every durable job ended after the kill",
        drained is not None,
        f"{sc.recovered_in_s and round(sc.recovered_in_s)} s after the kill"
        if drained is not None
        else f"jobs still open after {sc.recovery_bound_s:.0f} s",
    )
    with db() as conn:
        requeued = conn.execute(
            "SELECT count(*) FROM jasil_job_attempts WHERE outcome = 'lease_expired' AND id = ANY(%s)", (open_attempts,)
        ).fetchone()[0]
    sc.notes["attempts_ended_lease_expired"] = requeued
    sc.check(
        "the killed worker's attempts ended by lease expiry and their jobs were requeued",
        len(open_attempts) > 0 and requeued == len(open_attempts),
        f"{requeued} of the {len(open_attempts)} attempts open at the kill ended lease_expired; "
        "none of the jobs ran twice (invariants)",
    )
    sc.check("both workers run again", wait_for(lambda: replicas_healthy("worker", 2), 60) is not None)


def api_restart(sc: Scenario, ctx: "Context") -> None:
    """Restart one API replica while uploads are in flight."""
    uploads = ctx.uploads
    victim = container_ids("api")[0]
    thread = threading.Thread(target=uploads.burst, kwargs={"per_account": 6})
    thread.start()
    time.sleep(1.0)
    restarted = time.monotonic()
    docker("restart", victim)
    thread.join(timeout=120)
    sc.recovered_in_s = wait_for(lambda: replicas_healthy("api", 2) and healthy(), sc.recovery_bound_s)
    if sc.recovered_in_s is not None:
        sc.recovered_in_s = time.monotonic() - restarted
    sc.check(
        "the replica is healthy again and the proxy serves",
        sc.recovered_in_s is not None,
        f"{sc.recovered_in_s and round(sc.recovered_in_s)} s after the restart",
    )
    sc.notes["uploads_accepted"] = len(uploads.entries)
    sc.notes["uploads_cut_off"] = uploads.lost
    ended = uploads.settle(120)
    sc.check(
        "every accepted upload ended",
        ended is not None,
        f"{len(uploads.entries)} accepted, {uploads.lost} cut off in flight",
    )
    sc.check("none of them failed", all(e["status"] != "failed" for e in uploads.entries))


def redis_outage(sc: Scenario, ctx: "Context") -> None:
    """Stop Redis for 20 s and check the documented degradation, then the recovery."""
    client = Client(ctx.seed, ctx.seed["users"][-1], 120)
    sc.check("a client signed in before the outage", client.login().status_code == 200)
    compose("stop", "redis")
    outage = time.monotonic()
    probes = {"health_degraded": [], "read_ok": [], "ws_ticket": [], "login": []}
    while time.monotonic() - outage < 20:
        body = health()
        probes["health_degraded"].append(
            body is not None and body.get("status") == "degraded" and body.get("state") == "unavailable"
        )
        probes["read_ok"].append(client.get("/activities", params={"num_records": 1}).status_code)
        probes["ws_ticket"].append(client.post("/ws/ticket").status_code)
        probes["login"].append(Client(ctx.seed, ctx.seed["users"][-2], 121).login().status_code)
        time.sleep(2)
    sc.notes["during_outage"] = {
        "health_degraded": f"{sum(probes['health_degraded'])}/{len(probes['health_degraded'])}",
        "reads": sorted(set(probes["read_ok"])),
        "ws_ticket": sorted(set(probes["ws_ticket"])),
        "login": sorted(set(probes["login"])),
    }
    # docs/getting-started/monitoring.md: /health stays 200 with state "unavailable", most routes keep serving, and the
    # routes that need the shared state (WebSocket tickets) answer 503.
    sc.check(
        "/health answers 200 and says degraded, state unavailable",
        all(probes["health_degraded"]),
        str(probes["health_degraded"]),
    )
    sc.check("reads keep working (200)", set(probes["read_ok"]) == {200}, str(sorted(set(probes["read_ok"]))))
    sc.check("WebSocket tickets answer 503", set(probes["ws_ticket"]) == {503}, str(sorted(set(probes["ws_ticket"]))))
    sc.check(
        "sign-in answers 503 or 200, never a 5xx other than 503",
        set(probes["login"]) <= {200, 503},
        str(sorted(set(probes["login"]))),
    )
    compose("start", "redis")
    restored = time.monotonic()
    sc.recovered_in_s = wait_for(healthy, sc.recovery_bound_s)
    sc.check(
        "/health is ok again",
        sc.recovered_in_s is not None,
        f"{sc.recovered_in_s and round(sc.recovered_in_s)} s after Redis started",
    )
    ticket = wait_for(lambda: client.post("/ws/ticket").status_code == 201, sc.recovery_bound_s)
    sc.check("WebSocket tickets are issued again", ticket is not None, f"{ticket and round(ticket)} s")
    sc.check(
        "sign-in works again",
        wait_for(lambda: Client(ctx.seed, ctx.seed["users"][-2], 122).login().status_code == 200, 30) is not None,
    )
    sc.recovered_in_s = time.monotonic() - restored


def postgres_faults(sc: Scenario, ctx: "Context") -> None:
    """200 ms of latency for 30 s, then every PostgreSQL connection reset, under an upload burst."""
    proxy = f"{TOXIPROXY}/proxies/postgres/toxics"
    requests.delete(proxy + "/latency", timeout=5)
    requests.delete(proxy + "/reset", timeout=5)
    requests.post(
        proxy,
        json={
            "name": "latency",
            "type": "latency",
            "stream": "downstream",
            "toxicity": 1.0,
            "attributes": {"latency": 200, "jitter": 20},
        },
        timeout=5,
    ).raise_for_status()
    sc.notes["latency_ms"] = 200
    t0 = time.monotonic()
    uploads = ctx.uploads
    sender = threading.Thread(target=uploads.burst, kwargs={"per_account": 6})
    sender.start()
    latencies = []
    client = Client(ctx.seed, ctx.seed["users"][-1], 130)
    client.login()
    while time.monotonic() - t0 < 30:
        started = time.monotonic()
        client.get("/activities", params={"num_records": 5})
        latencies.append((time.monotonic() - started) * 1000)
        time.sleep(1)
    sender.join(timeout=120)
    sc.notes["read_latency_with_toxic_ms"] = round(sorted(latencies)[len(latencies) // 2])
    sc.check(
        "the latency toxic is felt (median read slower than 200 ms)",
        sc.notes["read_latency_with_toxic_ms"] >= 200,
        f"median {sc.notes['read_latency_with_toxic_ms']} ms",
    )
    requests.post(
        proxy,
        json={
            "name": "reset",
            "type": "reset_peer",
            "stream": "downstream",
            "toxicity": 1.0,
            "attributes": {"timeout": 0},
        },
        timeout=5,
    ).raise_for_status()
    time.sleep(10)
    during = health()
    sc.notes["health_during_resets"] = None if during is None else during.get("status")
    requests.delete(proxy + "/reset", timeout=5)
    requests.delete(proxy + "/latency", timeout=5)
    restored = time.monotonic()
    sc.recovered_in_s = wait_for(
        lambda: healthy() and client.get("/activities", params={"num_records": 1}).status_code == 200,
        sc.recovery_bound_s,
    )
    sc.check(
        "the application answers again after the toxics are removed",
        sc.recovered_in_s is not None,
        f"{sc.recovered_in_s and round(sc.recovered_in_s)} s",
    )
    sc.recovered_in_s = None if sc.recovered_in_s is None else time.monotonic() - restored

    def pool_recovered() -> bool:
        with db() as conn:
            total, stuck = conn.execute(
                "SELECT count(*), count(*) FILTER (WHERE state = 'idle in transaction' AND now() - state_change > interval '30 seconds') "
                "FROM pg_stat_activity WHERE datname = 'endurain'"
            ).fetchone()
        return stuck == 0 and total < 150

    sc.check(
        "no connection is stuck idle in a transaction and the pool is back under budget",
        wait_for(pool_recovered, 60) is not None,
    )
    ended = uploads.settle(sc.recovery_bound_s)
    sc.check(
        "every upload accepted around the faults ended",
        ended is not None,
        f"{len(uploads.entries)} accepted, {uploads.lost} cut off",
    )


def strava_429(sc: Scenario, ctx: "Context") -> None:
    """The stub answers 429 to every Strava call for a burst while syncs run; they must be deferred, not failed."""
    # Strava's 15-minute back-off of an earlier burst is kept in Redis; clear it so this burst is the first.
    keys = compose("exec", "-T", "redis", "redis-cli", "--scan", "--pattern", "*strava*").stdout.split()
    if keys:
        compose("exec", "-T", "redis", "redis-cli", "del", *keys)
    requests.post(f"{STUB}/strava/limit", json={"reject_for": 45}, timeout=5).raise_for_status()
    time.sleep(50)
    served = requests.get(f"{STUB}/stats", timeout=5).json()["served"]
    sc.notes["stub_served"] = served
    sc.check(
        "the stub answered 429 to the syncs of the burst",
        served.get("strava_429", 0) > 0,
        f"{served.get('strava_429', 0)} answers",
    )
    sc.recovered_in_s = 0.0
    # Which jobs ended how is checked by invariants.py: no failed refresh, every deferral carries retry_after, no attempt used.


# name -> (function, recovery bound in seconds, Locust run index, the Strava burst of the Locust load, fault mode of the invariants)
SCENARIOS: dict[str, tuple[Callable, float, int, str, bool]] = {
    # The lease is 45 s and the reaper runs every minute: a killed worker's jobs are back within ~2 minutes.
    "worker_kill": (worker_kill, 240.0, 1, "", False),
    "api_restart": (api_restart, 120.0, 2, "", True),
    # Redis comes back and the application reconnects on the next use.
    "redis_outage": (redis_outage, 60.0, 3, "", True),
    # The pool replaces its dropped connections on the next checkout; jobs retry with a 1-5 s back-off.
    "postgres_faults": (postgres_faults, 90.0, 4, "", True),
    "strava_429": (strava_429, 60.0, 5, "", False),
}


@dataclass
class Context:
    seed: dict
    uploads: Uploads


def run_scenario(run: str, name: str) -> dict:
    function, bound, run_index, burst, fault = SCENARIOS[name]
    sc = Scenario(name, bound)
    print(f"\n== {name} (recovery bound {bound:.0f} s)", flush=True)
    seed = json.loads(USERS_FILE.read_text())
    plain = [u for u in seed["users"] if not u.get("strava")] or seed["users"]
    uploads = Uploads(name, run_index, seed, plain[:3])
    requests.post(f"{STUB}/reset", timeout=5)
    started_at = db_now()
    started = time.monotonic()
    load = Load(run, name, run_index, burst)
    try:
        time.sleep(WARM_UP)
        function(sc, Context(seed, uploads))
        time.sleep(SETTLE)
    # A scenario that cannot run (docker, an HTTP call, the database) is a failed scenario, reported; a bug raises.
    except (subprocess.CalledProcessError, requests.RequestException, psycopg.Error, OSError) as err:
        sc.error = f"{type(err).__name__}: {err}"
        print(f"  scenario error: {sc.error}", flush=True)
    finally:
        # Whatever the scenario toxified or stopped is put back before the load stops and the invariants look.
        requests.delete(f"{TOXIPROXY}/proxies/postgres/toxics/latency", timeout=5)
        requests.delete(f"{TOXIPROXY}/proxies/postgres/toxics/reset", timeout=5)
        compose("start", "redis", check=False)
        compose("up", "-d", "--no-recreate", "--scale", "api=2", "--scale", "worker=2", "api", "worker", check=False)
        load.stop()
    # The driver's own uploads join the Locust ledger so the invariants cover them.
    ledger_path = RESULTS / run / name / "ledger.json"
    if ledger_path.exists():
        ledger = json.loads(ledger_path.read_text())
        ledger["uploads"] = ledger.get("uploads", []) + uploads.entries
        ledger_path.write_text(json.dumps(ledger, indent=2))
    print("  invariants", flush=True)
    report = invariants.check(DATABASE_URL, name, RESULTS / run, DRAIN_TIMEOUT, fault=fault, since=started_at)
    report.print()
    (RESULTS / run / name / "invariants.json").write_text(json.dumps(report.rows, indent=2))
    summary = load.summary().get("total", {})
    broken = [row["check"] for row in report.rows if row["result"] == "FAIL"]
    failed_assertions = [a["assertion"] for a in sc.assertions if not a["ok"]]
    ok = not broken and not failed_assertions and sc.error is None
    return {
        "scenario": name,
        "ok": ok,
        "duration_s": round(time.monotonic() - started),
        "recovery_bound_s": bound,
        "recovered_in_s": None if sc.recovered_in_s is None else round(sc.recovered_in_s, 1),
        "assertions": sc.assertions,
        "failed_assertions": failed_assertions,
        "invariants_violated": broken,
        "invariants_fault_mode": fault,
        "notes": sc.notes,
        "error": sc.error,
        "background_load": {key: summary.get(key) for key in ("requests", "failures", "throttled", "rps", "p95_ms")},
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--run", default="faults-manual")
    parser.add_argument("--only", default="", help="comma-separated scenarios; default all")
    args = parser.parse_args()
    names = [n for n in args.only.split(",") if n] or list(SCENARIOS)
    unknown = set(names) - set(SCENARIOS)
    if unknown:
        parser.error(f"unknown scenario(s): {', '.join(sorted(unknown))}")
    (RESULTS / args.run).mkdir(parents=True, exist_ok=True)
    out = RESULTS / args.run / "faults.json"
    outcomes: list[dict] = []
    for name in names:
        outcomes.append(run_scenario(args.run, name))
        out.write_text(
            json.dumps({"run": args.run, "ok": all(o["ok"] for o in outcomes), "scenarios": outcomes}, indent=2)
        )
    print("\nfault scenarios")
    for outcome in outcomes:
        print(
            f"  {'ok  ' if outcome['ok'] else 'FAIL'} {outcome['scenario']:<16} recovered in {outcome['recovered_in_s']} s "
            f"(bound {outcome['recovery_bound_s']:.0f} s)"
            + (
                ""
                if outcome["ok"]
                else f"  <- {outcome['failed_assertions'] + outcome['invariants_violated'] + ([outcome['error']] if outcome['error'] else [])}"
            )
        )
    return 0 if all(o["ok"] for o in outcomes) else 1


if __name__ == "__main__":
    sys.exit(main())
