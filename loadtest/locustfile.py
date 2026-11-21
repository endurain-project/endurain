"""Locust scenarios for a distributed Endurain deployment, with threshold gates and a machine-readable summary.

Run through ``run.sh``; by hand::

    LOADTEST_RUN=manual uv run locust -f locustfile.py --headless -u 20 -r 5 -t 2m \
        --host http://localhost:18080 --csv results/manual/locust

Every request is named ``<group> <METHOD> <path template>``; ``thresholds.json`` gates a run per group. A ``429`` is the
server's rate limiter working, so it is counted apart (``throttled``) and is neither a success nor a failure.

One Locust process only: the ledger of what the run created lives in this process and is written to
``results/<run>/ledger.json`` for ``invariants.py``.
"""

import itertools
import json
import logging
import os
import random
import time
import uuid
from datetime import UTC, datetime, timedelta
from http.cookies import SimpleCookie
from pathlib import Path

import gevent
import gpxgen
import requests
import websocket
from gevent.event import Event
from locust import HttpUser, between, constant, events, task
from locust.stats import StatsEntry

# The upload burst sends many requests from one user's connection pool; the discarded connections are not news.
logging.getLogger("urllib3.connectionpool").setLevel(logging.ERROR)

HERE = Path(__file__).resolve().parent
RUN = os.environ.get("LOADTEST_RUN", "manual")
RESULTS = Path(os.environ.get("LOADTEST_RESULTS", HERE / "results")) / RUN
USERS_FILE = Path(os.environ.get("LOADTEST_USERS_FILE", HERE / "data" / "users.json"))
THRESHOLDS_FILE = Path(os.environ.get("LOADTEST_THRESHOLDS", HERE / "thresholds.json"))
#: Must equal ENDURAIN_HOST of the deployment: the origin check of the cookie routes and of the WebSocket compares it.
ORIGIN = os.environ.get("LOADTEST_ORIGIN", "http://localhost:18080")
#: Distinguishes the runs of one stack (the scale profile reuses its database), so dates and files never repeat.
RUN_INDEX = int(os.environ.get("LOADTEST_RUN_INDEX", "0"))
#: Open uploads one account may have at once (the server's cap); the run checks it is never exceeded.
UPLOAD_CAP = 10
#: The stub providers' admin API (stub/stub.py): where the Strava rate-limit burst is asked for and the counters read.
STUB_ADMIN = os.environ.get("LOADTEST_STUB_ADMIN", "http://localhost:18081")
#: ``<seconds after the start>:<seconds>``: when the stub starts answering every Strava call with 429, and for how long.
#: Empty turns the burst off.
STRAVA_BURST = os.environ.get("LOADTEST_STRAVA_BURST", "40:30")
#: Sessions of one Strava account that ask for a sync independently, so two syncs of one account overlap.
STRAVA_SESSIONS_PER_ACCOUNT = 2
#: Virtual users that share one account in the Idempotency-Key collision scenario.
COLLISION_GROUP_SIZE = 4

SEED = json.loads(USERS_FILE.read_text()) if USERS_FILE.exists() else {"password": "", "users": []}
_vid_counter = itertools.count()
_collision_counter = itertools.count()
_strava_counter = itertools.count()

#: What the run did, for ``invariants.py``. Appends are atomic under gevent, so no lock.
LEDGER: dict[str, list] = {
    "gears": [],  # {key, nickname, user_id, statuses}
    "weights": [],  # {id, user_id, deleted}: deleted is None while the outcome of the DELETE is unknown
    "steps": [],  # {id, user_id}
    "uploads": [],  # {job_id, key, user_id, status, activity_ids}
    "upload_key_violations": [],  # {key, job_ids}
    "idempotency_violations": [],  # {key, detail}
    "refreshes": [],  # {job_id, user_id, status, retry_after}: a Strava refresh job and where it ended
    "strava_bursts": [],  # {at, seconds}: a window in which the stub answered every Strava call with 429
}
THROTTLED: dict[str, int] = {}
STARTED = {"at": 0.0, "ws_established": 0, "ws_closed": {}}


def _client_ip(vid: int) -> str:
    """The address a virtual user pretends to come from, so per-client limits see many clients."""
    return f"10.{(vid >> 8) & 255}.{vid & 255}.{random.Random(vid).randint(2, 250)}"


def gpx(vid: int, n: int, points: int = 600) -> bytes:
    """A unique, valid GPX run for one upload of one virtual user in this run (see :func:`gpxgen.gpx`)."""
    return gpxgen.gpx(vid, n, RUN_INDEX, points)


def _cookie_header(jar: dict[str, str]) -> str:
    return "; ".join(f"{name}={value}" for name, value in jar.items())


class ApiUser(HttpUser):
    """A signed-in web client of one seeded account: logs in, keeps its tokens fresh, and wraps every call."""

    abstract = True
    wait_time = constant(1.0)

    #: Number of the account to use; subclasses may pick their own.
    def account(self) -> dict:
        users = SEED["users"]
        return users[self.vid % len(users)]

    def on_start(self) -> None:
        self.vid = next(_vid_counter)
        self.ip = _client_ip(self.vid)
        self.account_info = self.account()
        self.user_id = self.account_info["user_id"]
        self.cookies: dict[str, str] = {}
        self.token = ""
        self.token_exp = 0.0
        self.client.cookies.clear()
        self.login(retries=6)

    # -- auth ---------------------------------------------------------------------------------------------------

    def _store_tokens(self, resp) -> None:
        body = resp.json()
        self.token = body["access_token"]
        self.token_exp = time.monotonic() + body["expires_in"] - 60
        # A Secure cookie is not replayed over plain http by a cookie jar, so the cookies are carried by hand.
        for header in resp.raw.headers.getlist("set-cookie"):
            parsed = SimpleCookie()
            parsed.load(header)
            for name, morsel in parsed.items():
                if morsel.value:
                    self.cookies[name] = morsel.value
                else:
                    self.cookies.pop(name, None)

    def _base_headers(self) -> dict[str, str]:
        return {"X-LoadTest-Client-IP": self.ip, "X-Client-Type": "web"}

    def login(self, *, retries: int = 1) -> bool:
        """Sign in with the account's password; a throttled attempt waits for ``Retry-After`` and tries again."""
        for _ in range(retries):
            with self.client.post(
                "/api/v1/auth/login",
                name="auth_login POST /auth/login",
                data={"username": self.account_info["username"], "password": SEED["password"]},
                headers={**self._base_headers(), "Cookie": _cookie_header(self.cookies)},
                catch_response=True,
            ) as resp:
                if resp.status_code == 200 and resp.json().get("next_step") == "tokens":
                    self._store_tokens(resp)
                    resp.success()
                    return True
                if resp.status_code == 429:
                    _throttled(resp, "auth_login POST /auth/login")
                    gevent.sleep(min(float(resp.headers.get("Retry-After", 5)), 30))
                    continue
                resp.failure(f"login {resp.status_code}: {resp.text[:200]}")
                return False
        return False

    def refresh(self) -> bool:
        """Renew the tokens with the refresh cookie, as the web app does on reload, with the origin the server checks."""
        with self.client.post(
            "/api/v1/auth/refresh",
            name="auth_refresh POST /auth/refresh",
            headers={**self._base_headers(), "Origin": ORIGIN, "Cookie": _cookie_header(self.cookies)},
            catch_response=True,
        ) as resp:
            if resp.status_code == 200:
                self._store_tokens(resp)
                resp.success()
                return True
            if resp.status_code == 429:
                _throttled(resp, "auth_refresh POST /auth/refresh")
                return False
            resp.failure(f"refresh {resp.status_code}: {resp.text[:200]}")
            return False

    # -- requests -----------------------------------------------------------------------------------------------

    def api(self, method: str, path: str, name: str, *, ok: tuple[int, ...] = (200,), **kwargs):
        """Call the API as this user; return the response (a throttled call returns it too, with ``status 429``).

        The access token is renewed before it expires and once on an ``invalid-token`` 401. A status outside ``ok``
        is a failure of ``name``.
        """
        if time.monotonic() > self.token_exp:
            self.refresh()
        headers = {**self._base_headers(), "Authorization": f"Bearer {self.token}", **kwargs.pop("headers", {})}
        headers.pop("X-Client-Type", None)
        for attempt in (0, 1):
            with self.client.request(
                method, f"/api/v1{path}", name=name, headers=headers, catch_response=True, **kwargs
            ) as resp:
                if resp.status_code in ok:
                    resp.success()
                    return resp
                if resp.status_code == 429:
                    _throttled(resp, name)
                    return resp
                if resp.status_code == 401 and attempt == 0 and "invalid-token" in resp.text:
                    resp.success()  # the expiry of the token is the web app's normal path, not an error
                    if self.refresh():
                        headers["Authorization"] = f"Bearer {self.token}"
                        continue
                resp.failure(f"{resp.status_code}: {resp.text[:200]}")
                return resp
        return resp

    def get_json(self, path: str, name: str, **kwargs):
        """GET and parse; None when the call did not succeed."""
        resp = self.api("GET", path, name, **kwargs)
        return resp.json() if resp.status_code == 200 else None


def _throttled(resp, name: str) -> None:
    """Count a 429 apart: the rate limiter doing its job is neither a success nor a failure of the endpoint."""
    resp.success()
    THROTTLED[name] = THROTTLED.get(name, 0) + 1


# ------------------------------------------------------------------------------------------------------------------
# Browse, health, notifications
# ------------------------------------------------------------------------------------------------------------------


class AthleteUser(ApiUser):
    """The everyday user: browses the feed and activities, reads and writes health data, reads notifications."""

    weight = 10
    wait_time = between(0.8, 2.0)

    def on_start(self) -> None:
        super().on_start()
        self.activity_ids = [a["id"] for a in self.account_info.get("activities", [])]
        self.streamed = [a["id"] for a in self.account_info.get("activities", []) if a["streams"]]
        self.lapped = [a["id"] for a in self.account_info.get("activities", []) if a["laps"]]
        self.feed_cursor: str | None = None
        self.steps_used = 0
        self.weight_day = (datetime.now(UTC) - timedelta(days=400 + (self.vid % 100) * 3)).date().isoformat()

    # -- browse --------------------------------------------------------------------------------------------------

    @task(10)
    def feed(self) -> None:
        params = {"num_records": 20, "scope": random.choice(["following", "following", "mine"])}
        if self.feed_cursor and random.random() < 0.4:
            params["cursor"] = self.feed_cursor
        body = self.get_json("/activities/feed", "browse GET /activities/feed", params=params)
        self.feed_cursor = (body or {}).get("next_cursor")

    @task(8)
    def activity_list(self) -> None:
        params: dict[str, object] = {
            "num_records": 20,
            "page_number": random.randint(1, 4),
            "sort_by": random.choice(["start_time", "distance", "duration"]),
            "sort_order": random.choice(["desc", "asc"]),
        }
        if random.random() < 0.5:
            params["type"] = random.choice(["run", "ride", "walk"])
        if random.random() < 0.3:
            params["name_contains"] = random.choice(["Run", "Ride", "Walk"])
        if random.random() < 0.3:
            end = datetime.now(UTC) - timedelta(days=random.randint(0, 120))
            params["start_date"] = (end - timedelta(days=60)).date().isoformat()
            params["end_date"] = end.date().isoformat()
        self.get_json("/activities", "browse GET /activities (filtered)", params=params)

    @task(6)
    def activity_detail(self) -> None:
        if self.activity_ids:
            activity_id = random.choice(self.activity_ids)
            self.get_json(f"/activities/{activity_id}/detail", "browse GET /activities/{id}/detail")

    @task(3)
    def activity_streams(self) -> None:
        if self.streamed:
            activity_id = random.choice(self.streamed)
            self.get_json(f"/activities/{activity_id}/streams", "browse GET /activities/{id}/streams")
            if random.random() < 0.5:
                self.get_json(
                    f"/activities/{activity_id}/streams/heart_rate", "browse GET /activities/{id}/streams/{type}"
                )

    @task(3)
    def activity_laps(self) -> None:
        if self.lapped:
            self.get_json(f"/activities/{random.choice(self.lapped)}/laps", "browse GET /activities/{id}/laps")

    @task(2)
    def summaries(self) -> None:
        self.get_json(
            "/activities/summaries",
            "browse GET /activities/summaries",
            params={"period": random.choice(["week", "month"]), "date": datetime.now(UTC).date().isoformat()},
        )

    @task(1)
    def gears(self) -> None:
        self.get_json("/gears", "browse GET /gears", params={"num_records": 20})

    # -- health --------------------------------------------------------------------------------------------------

    @task(5)
    def health_reads(self) -> None:
        kind = random.choice(["weight", "steps", "sleep", "water"])
        self.get_json(f"/health/{kind}", "health_read GET /health/{kind}", params={"num_records": 30})
        if random.random() < 0.4:
            self.get_json(
                f"/health/{kind}/chart",
                "health_read GET /health/{kind}/chart",
                params={"interval": random.choice(["last_30_days", "last_90_days", "last_year"])},
            )
        if random.random() < 0.3:
            self.get_json("/health/stats/daily", "health_read GET /health/stats/daily")

    @task(3)
    def weight_lifecycle(self) -> None:
        """Create a weight with an Idempotency-Key, replay it, edit it with the ETag it was given, delete it."""
        key = f'"{uuid.uuid4()}"'
        body = {"date": self.weight_day, "weight_kg": round(random.uniform(60, 90), 1)}
        created = self.api(
            "POST",
            "/health/weight",
            "health_write POST /health/weight",
            ok=(201,),
            json=body,
            headers={"Idempotency-Key": key},
        )
        if created.status_code != 201:
            return
        record = created.json()
        entry = {"id": record["id"], "user_id": self.user_id, "deleted": False}
        LEDGER["weights"].append(entry)
        if random.random() < 0.3:  # a client that never saw the answer sends it again
            replay = self.api(
                "POST",
                "/health/weight",
                "health_write POST /health/weight (replay)",
                ok=(201, 409),
                json=body,
                headers={"Idempotency-Key": key},
            )
            if replay.status_code == 201 and replay.json().get("id") != record["id"]:
                LEDGER["idempotency_violations"].append({"key": key, "detail": "replay returned another record"})
        etag = created.headers.get("ETag")
        patched = self.api(
            "PATCH",
            f"/health/weight/{record['id']}",
            "health_write PATCH /health/weight/{id}",
            json={"weight_kg": round(random.uniform(60, 90), 1)},
            headers={"If-Match": etag},
        )
        etag = patched.headers.get("ETag", etag)
        # Unknown until an answer says otherwise: a DELETE cut off by the end of the run or answered 5xx may have
        # committed.
        entry["deleted"] = None
        deleted = self.api(
            "DELETE",
            f"/health/weight/{record['id']}",
            "health_write DELETE /health/weight/{id}",
            ok=(204,),
            headers={"If-Match": etag},
        )
        if deleted.status_code < 500:
            entry["deleted"] = deleted.status_code == 204

    @task(2)
    def steps_create(self) -> None:
        """Record steps for a day nobody else uses and keep them, so the run's creates can be counted afterwards."""
        if self.steps_used >= 20:
            return
        offset = 100 + RUN_INDEX * 2000 + (self.vid % 100) * 20 + self.steps_used
        day = (datetime.now(UTC) - timedelta(days=offset)).date().isoformat()
        self.steps_used += 1
        created = self.api(
            "POST",
            "/health/steps",
            "health_write POST /health/steps",
            ok=(201, 409),
            json={"date": day, "steps": random.randint(1000, 20000)},
            headers={"Idempotency-Key": f'"{uuid.uuid4()}"'},
        )
        if created.status_code == 201:
            LEDGER["steps"].append({"id": created.json()["id"], "user_id": self.user_id})

    # -- notifications -------------------------------------------------------------------------------------------

    @task(4)
    def notifications(self) -> None:
        self.get_json("/notifications/unread-count", "notifications GET /notifications/unread-count")
        if random.random() < 0.5:
            self.get_json("/notifications", "notifications GET /notifications", params={"num_records": 20})


# ------------------------------------------------------------------------------------------------------------------
# Uploads
# ------------------------------------------------------------------------------------------------------------------


class UploadMixin:
    """Upload GPX files and follow their jobs to the end."""

    def post_upload(self, *, repeat_key: bool = False) -> dict | None:
        """Upload one unique GPX with an Idempotency-Key; return its ledger entry, or None when it was not accepted."""
        self.upload_n = getattr(self, "upload_n", 0) + 1
        n = self.upload_n
        data = gpx(self.vid, n)
        key = f'"{uuid.uuid4()}"'
        name = f"load-{RUN}-{self.vid}-{n}.gpx"
        resp = self.api(
            "POST",
            "/activities/upload",
            "upload POST /activities/upload",
            ok=(202, 409),
            files={"file": (name, data, "application/gpx+xml")},
            headers={"Idempotency-Key": key},
        )
        if resp.status_code != 202:  # 409: the account has its cap of open uploads; 429: throttled
            return None
        job_id = resp.json()["id"]
        entry = {
            "job_id": job_id,
            "key": key,
            "user_id": self.user_id,
            "status": "queued",
            "activity_ids": [],
            "bytes": len(data),
        }
        LEDGER["uploads"].append(entry)
        if repeat_key:  # the same file again with the same key must answer the same job
            again = self.api(
                "POST",
                "/activities/upload",
                "upload POST /activities/upload (replay)",
                ok=(202,),
                files={"file": (name, data, "application/gpx+xml")},
                headers={"Idempotency-Key": key},
            )
            if again.status_code == 202 and again.json()["id"] != job_id:
                LEDGER["upload_key_violations"].append({"key": key, "job_ids": [job_id, again.json()["id"]]})
        return entry

    def wait_job(self, entry: dict, timeout: float = 180) -> str:
        """Poll the entry's job until it ends; record the outcome on the entry and return its status."""
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            gevent.sleep(random.uniform(1.0, 2.0))
            body = self.get_json(f"/jobs/{entry['job_id']}", "upload GET /jobs/{id}")
            if body is not None and body["status"] in ("succeeded", "failed"):
                entry.update(status=body["status"], activity_ids=body.get("activity_ids") or [])
                break
        return entry["status"]

    def upload_gpx(self, *, repeat_key: bool = False) -> tuple[str | None, str]:
        """Upload one file and follow its job; return ``(job id, final status)``."""
        started = time.monotonic()
        entry = self.post_upload(repeat_key=repeat_key)
        if entry is None:
            return None, "not-accepted"
        status = self.wait_job(entry)
        events.request.fire(
            request_type="E2E",
            name="upload_e2e accepted -> succeeded",
            response_time=(time.monotonic() - started) * 1000,
            response_length=entry["bytes"],
            exception=None if status == "succeeded" else RuntimeError(f"upload ended {status}"),
            context={},
        )
        return entry["job_id"], status

    def upload_burst(self, count: int = UPLOAD_CAP + 2) -> None:
        """Send more uploads at once than the account may have open; the cap must hold under concurrency."""
        greenlets = [gevent.spawn(self.post_upload) for _ in range(count)]
        gevent.joinall(greenlets, timeout=60)
        entries = [g.value for g in greenlets if g.value is not None]
        gevent.joinall([gevent.spawn(self.wait_job, e) for e in entries], timeout=200)


class UploaderUser(UploadMixin, ApiUser):
    """Uploads GPX files one after another, as a user syncing a watch does."""

    weight = 2
    wait_time = between(2.0, 6.0)

    @task(10)
    def upload(self) -> None:
        self.upload_gpx(repeat_key=random.random() < 0.2)

    @task(3)
    def burst(self) -> None:
        self.upload_burst()


# ------------------------------------------------------------------------------------------------------------------
# Strava sync (against the stub)
# ------------------------------------------------------------------------------------------------------------------


class StravaUser(ApiUser):
    """Asks for a sync of the last day of the account's Strava, as the refresh button does, and follows the job.

    The accounts are the seeded ones linked to the stub Strava. A job ends ``succeeded``, ``failed``, or deferred
    (``queued`` with ``retry_after``) when Strava answered 429: a deferral is the documented outcome, not a failure.
    Several sessions of one account may ask at once, which is how a duplicate per Strava id would show.
    """

    fixed_count = STRAVA_SESSIONS_PER_ACCOUNT * 2  # two accounts at least, whatever the user count
    wait_time = between(4.0, 10.0)

    def account(self) -> dict:
        linked = [user for user in SEED["users"] if user.get("strava")] or SEED["users"]
        return linked[(next(_strava_counter) // STRAVA_SESSIONS_PER_ACCOUNT) % len(linked)]

    @task
    def refresh_strava(self) -> None:
        started = time.monotonic()
        resp = self.api("POST", "/activities/refresh", "strava POST /activities/refresh", ok=(202,))
        if resp.status_code != 202:
            return
        entry = {"job_id": resp.json()["id"], "user_id": self.user_id, "status": "queued", "retry_after": None}
        LEDGER["refreshes"].append(entry)
        deadline = time.monotonic() + 120
        while time.monotonic() < deadline:
            gevent.sleep(random.uniform(1.0, 2.0))
            body = self.get_json(f"/jobs/{entry['job_id']}", "strava_job GET /jobs/{id}")
            if body is None:
                continue
            entry.update(status=body["status"], retry_after=body.get("retry_after"))
            if body["status"] in ("succeeded", "failed") or body.get("retry_after"):
                break
        settled = entry["status"] == "succeeded" or bool(entry["retry_after"])
        events.request.fire(
            request_type="E2E",
            name="strava_e2e refresh accepted -> settled",
            response_time=(time.monotonic() - started) * 1000,
            response_length=0,
            exception=None if settled else RuntimeError(f"refresh ended {entry['status']}"),
            context={},
        )


def _strava_burst(after: float, seconds: float) -> None:
    """Ask the stub to answer every Strava call with 429 for a while, once, ``after`` seconds into the run."""
    gevent.sleep(after)
    try:
        requests.post(f"{STUB_ADMIN}/strava/limit", json={"reject_for": seconds}, timeout=10).raise_for_status()
        LEDGER["strava_bursts"].append({"at": time.time(), "seconds": seconds})
    except requests.RequestException as err:
        print(f"strava burst not started: {err}")


# ------------------------------------------------------------------------------------------------------------------
# Login and refresh storms
# ------------------------------------------------------------------------------------------------------------------


class AuthStormUser(ApiUser):
    """Signs in, refreshes several times and signs out again, in a loop, from a few shared client addresses.

    The shared addresses make the per-client limits bite, as a credential-stuffing or restart storm does; the
    ``429`` answers are counted as throttled.
    """

    weight = 1
    wait_time = between(0.2, 0.8)

    def on_start(self) -> None:
        super().on_start()
        self.ip = f"10.250.0.{self.vid % 3 + 1}"

    @task
    def storm(self) -> None:
        if not self.login():
            return
        for _ in range(random.randint(2, 5)):
            self.refresh()
            gevent.sleep(random.uniform(0.1, 0.4))
        with self.client.post(
            "/api/v1/auth/logout",
            name="auth_logout POST /auth/logout",
            headers={
                **self._base_headers(),
                "Origin": ORIGIN,
                "Cookie": _cookie_header(self.cookies),
                "Authorization": f"Bearer {self.token}",
            },
            catch_response=True,
        ) as resp:
            if resp.status_code in (200, 204):
                resp.success()
                self.cookies.clear()
            elif resp.status_code == 429:
                _throttled(resp, "auth_logout POST /auth/logout")
            else:
                resp.failure(f"logout {resp.status_code}: {resp.text[:200]}")


# ------------------------------------------------------------------------------------------------------------------
# Idempotency-Key collisions
# ------------------------------------------------------------------------------------------------------------------

_rounds: dict[tuple[int, int], dict] = {}


class CollisionUser(ApiUser):
    """Several sessions of one account fire the same create with the same key at the same moment.

    Exactly one record per key must result, whichever replica each request lands on. The answers may be ``201`` (the
    winner or a replay of its stored answer) or ``409`` (the winner is still running); ``invariants.py`` then counts
    the gears of each key in the database.
    """

    fixed_count = COLLISION_GROUP_SIZE  # one full group at least, whatever the user count
    wait_time = constant(0.5)

    def account(self) -> dict:
        self.collide_group = next(_collision_counter) // COLLISION_GROUP_SIZE
        users = SEED["users"]
        return users[self.collide_group % len(users)]

    def on_start(self) -> None:
        super().on_start()
        self.round = 0

    @task
    def collide(self) -> None:
        self.round += 1
        slot = _rounds.setdefault((self.collide_group, self.round), {"arrived": 0, "event": Event()})
        slot["arrived"] += 1
        if slot["arrived"] >= COLLISION_GROUP_SIZE:
            slot["event"].set()
        slot["event"].wait(timeout=15)
        key_text = f"{RUN}-g{self.collide_group}-r{self.round}"
        nickname = f"lt-run-{key_text}"
        entry = next((e for e in LEDGER["gears"] if e["key"] == key_text), None)
        if entry is None:
            entry = {"key": key_text, "nickname": nickname, "user_id": self.user_id, "statuses": []}
            LEDGER["gears"].append(entry)
        resp = self.api(
            "POST",
            "/gears",
            "idempotency POST /gears (same key, concurrent)",
            ok=(201, 409),
            json={"nickname": nickname, "gear_type": "bike"},
            headers={"Idempotency-Key": f'"{key_text}"'},
        )
        entry["statuses"].append(resp.status_code)
        if resp.status_code == 409:  # in flight: the documented answer is to wait and repeat
            gevent.sleep(1.2)
            resp = self.api(
                "POST",
                "/gears",
                "idempotency POST /gears (retry after 409)",
                ok=(201,),
                json={"nickname": nickname, "gear_type": "bike"},
                headers={"Idempotency-Key": f'"{key_text}"'},
            )
            entry["statuses"].append(resp.status_code)
        _rounds.pop((self.collide_group, self.round - 1), None)
        gevent.sleep(random.uniform(1.0, 3.0))


# ------------------------------------------------------------------------------------------------------------------
# WebSocket
# ------------------------------------------------------------------------------------------------------------------


class WebSocketUser(UploadMixin, ApiUser):
    """Holds a live-update socket: asks for a ticket, connects, waits for hints, reconnects.

    Each connection attempt is a ``websocket CONNECT`` request (a ``1013`` close, the handshake limit, is counted as
    throttled). Now and then it uploads a file and waits for the ``JOB_STATUS_CHANGED`` hint, which crosses from the
    worker through Redis to whichever replica holds this socket (``websocket_hint``).
    """

    weight = 2
    wait_time = constant(1)

    def on_start(self) -> None:
        super().on_start()
        self.ws = None

    def on_stop(self) -> None:
        self._close()

    def _close(self) -> None:
        if self.ws is not None:
            try:
                self.ws.close()
            except (websocket.WebSocketException, OSError):
                pass  # the peer may be gone already
            self.ws = None

    def _connect(self) -> bool:
        ticket_resp = self.api("POST", "/ws/ticket", "websocket POST /ws/ticket", ok=(201,))
        if ticket_resp.status_code != 201:
            return False
        url = ORIGIN.replace("http", "ws", 1) + "/api/v1/ws?ticket=" + ticket_resp.json()["ticket"]
        started = time.monotonic()
        error: Exception | None = None
        try:
            self.ws = websocket.create_connection(
                url, origin=ORIGIN, header=[f"X-LoadTest-Client-IP: {self.ip}"], timeout=10
            )
            # An accepted socket stays quiet; a refused one is closed by the server straight away.
            self.ws.settimeout(0.5)
            try:
                frame = self.ws.recv()
            except websocket.WebSocketTimeoutException:
                frame = None
            if frame is not None and frame == "":
                raise websocket.WebSocketConnectionClosedException("closed at the handshake")
        except websocket.WebSocketBadStatusException as err:
            error = err
        except (websocket.WebSocketException, OSError) as err:  # every failure to hold a socket is the measurement
            error = err
        elapsed = (time.monotonic() - started) * 1000
        if error is not None:
            self._close()
        events.request.fire(
            request_type="WS",
            name="websocket CONNECT /ws",
            response_time=elapsed,
            response_length=0,
            exception=error,
            context={},
        )
        if error is None:
            STARTED["ws_established"] += 1
        return error is None

    @task
    def hold_socket(self) -> None:
        if not self._connect():
            gevent.sleep(5)
            return
        hold_until = time.monotonic() + random.uniform(20, 40)
        hinted = False
        while time.monotonic() < hold_until:
            if not hinted and random.random() < 0.5:
                hinted = True
                self._upload_and_wait_for_hint()
            try:
                self.ws.settimeout(1.0)
                frame = self.ws.recv()
            except websocket.WebSocketTimeoutException:
                continue
            except (websocket.WebSocketConnectionClosedException, OSError) as err:
                code = getattr(err, "status_code", "closed")
                STARTED["ws_closed"][str(code)] = STARTED["ws_closed"].get(str(code), 0) + 1
                break
            if not frame:
                break
        self._close()

    def _upload_and_wait_for_hint(self) -> None:
        """Upload a file; the hint for its job must reach this socket."""
        job: dict = {}

        def upload() -> None:
            job["id"], job["status"] = self.upload_gpx()

        started = time.monotonic()
        uploader = gevent.spawn(upload)
        seen = False
        while not uploader.dead or not seen:
            if time.monotonic() - started > 90:
                break
            try:
                self.ws.settimeout(1.0)
                frame = self.ws.recv()
            except websocket.WebSocketTimeoutException:
                if uploader.dead and job.get("id") is None:
                    return  # no job was accepted (capped or throttled): nothing to wait for
                continue
            except (websocket.WebSocketException, OSError):
                break
            if frame and "JOB_STATUS_CHANGED" in frame:
                seen = True
                break
        if job.get("id") is None and uploader.dead:
            return
        events.request.fire(
            request_type="WS",
            name="websocket_hint JOB_STATUS_CHANGED after upload",
            response_time=(time.monotonic() - started) * 1000,
            response_length=0,
            exception=None if seen else RuntimeError("no JOB_STATUS_CHANGED hint reached the socket"),
            context={},
        )
        uploader.join(timeout=120)


# ------------------------------------------------------------------------------------------------------------------
# Gates and summary
# ------------------------------------------------------------------------------------------------------------------


def _group(name: str) -> str:
    return name.split(" ", 1)[0]


@events.test_start.add_listener
def _started(environment, **_kwargs) -> None:
    STARTED["at"] = time.time()
    RESULTS.mkdir(parents=True, exist_ok=True)
    if STRAVA_BURST and any(user.get("strava") for user in SEED["users"]):
        after, seconds = (float(part) for part in STRAVA_BURST.split(":"))
        gevent.spawn(_strava_burst, after, seconds)


def _summarise(environment) -> dict:
    stats = environment.stats
    duration = max((stats.last_request_timestamp or time.time()) - (stats.start_time or time.time()), 1.0)
    endpoints: dict[str, dict] = {}
    groups: dict[str, StatsEntry] = {}
    for key, entry in sorted(stats.entries.items()):
        name = entry.name
        endpoints[name] = {
            "method": entry.method,
            "requests": entry.num_requests,
            "failures": entry.num_failures,
            "error_rate": round(entry.fail_ratio, 5),
            "throttled": THROTTLED.get(name, 0),
            "rps": round(entry.num_requests / duration, 3),
            "p50_ms": entry.get_response_time_percentile(0.50),
            "p95_ms": entry.get_response_time_percentile(0.95),
            "p99_ms": entry.get_response_time_percentile(0.99),
            "avg_ms": round(entry.avg_response_time, 1),
            "max_ms": entry.max_response_time,
        }
        merged = groups.setdefault(_group(name), StatsEntry(stats, _group(name), ""))
        merged.extend(entry)
    thresholds = json.loads(THRESHOLDS_FILE.read_text())
    default = thresholds.get("default", {})
    minimum = thresholds.get("min_requests", 10)
    group_rows: dict[str, dict] = {}
    violations: list[str] = []
    for group, merged in sorted(groups.items()):
        limit = {**default, **thresholds.get("groups", {}).get(group, {})}
        throttled = sum(v for k, v in THROTTLED.items() if _group(k) == group)
        row = {
            "requests": merged.num_requests,
            "failures": merged.num_failures,
            "error_rate": round(merged.fail_ratio, 5),
            "throttled": throttled,
            "rps": round(merged.num_requests / duration, 3),
            "p50_ms": merged.get_response_time_percentile(0.50),
            "p95_ms": merged.get_response_time_percentile(0.95),
            "p99_ms": merged.get_response_time_percentile(0.99),
            "limit": limit,
            "status": "ok",
        }
        if merged.num_requests < minimum:
            row["status"] = "skipped"
        else:
            if "p95_ms" in limit and row["p95_ms"] > limit["p95_ms"]:
                row["status"] = "fail"
                violations.append(f"{group}: p95 {row['p95_ms']} ms > {limit['p95_ms']} ms")
            if "max_error_rate" in limit and row["error_rate"] > limit["max_error_rate"]:
                row["status"] = "fail"
                violations.append(f"{group}: error rate {row['error_rate']:.2%} > {limit['max_error_rate']:.2%}")
        group_rows[group] = row
    total = stats.total
    return {
        "run": RUN,
        "duration_s": round(duration, 1),
        "total": {
            "requests": total.num_requests,
            "failures": total.num_failures,
            "error_rate": round(total.fail_ratio, 5),
            "throttled": sum(THROTTLED.values()),
            "rps": round(total.num_requests / duration, 3),
            "p50_ms": total.get_response_time_percentile(0.50),
            "p95_ms": total.get_response_time_percentile(0.95),
            "p99_ms": total.get_response_time_percentile(0.99),
        },
        "websocket": {"established": STARTED["ws_established"], "closed_by_code": STARTED["ws_closed"]},
        "groups": group_rows,
        "endpoints": endpoints,
        "violations": violations,
    }


@events.quitting.add_listener
def _quitting(environment, **_kwargs) -> None:
    """Write summary.json and the ledger; fail the run when a group is over its threshold."""
    RESULTS.mkdir(parents=True, exist_ok=True)
    summary = _summarise(environment)
    (RESULTS / "summary.json").write_text(json.dumps(summary, indent=2))
    try:  # what the stub served, for the Strava checks of invariants.py
        stub = requests.get(f"{STUB_ADMIN}/stats", timeout=10).json()
    except (requests.RequestException, ValueError):
        stub = {}
    (RESULTS / "ledger.json").write_text(json.dumps({"run": RUN, **LEDGER, "stub": stub}, indent=2))
    print("\nLoad test summary (per group)")
    print(f"{'group':<14}{'reqs':>8}{'fail%':>8}{'429':>7}{'rps':>8}{'p50':>7}{'p95':>7}{'p99':>7}  limit   status")
    for group, row in summary["groups"].items():
        print(
            f"{group:<14}{row['requests']:>8}{row['error_rate'] * 100:>8.2f}{row['throttled']:>7}{row['rps']:>8.1f}"
            f"{row['p50_ms']:>7}{row['p95_ms']:>7}{row['p99_ms']:>7}  p95<={row['limit'].get('p95_ms', '-')}"
            f" err<={row['limit'].get('max_error_rate', '-')}  {row['status']}"
        )
    for violation in summary["violations"]:
        print(f"THRESHOLD VIOLATION: {violation}")
    if summary["violations"]:
        environment.process_exit_code = 1
    else:
        environment.process_exit_code = 0
