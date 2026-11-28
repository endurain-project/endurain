"""Check the database against the invariants a distributed Endurain must keep under load.

Read-only: the connection is opened read-only and nothing is written but ``results/<run>/invariants.json``. Exits
non-zero when an invariant is violated.

    uv run python invariants.py --run smoke

The idempotency records themselves live in the platform state (Redis), not in a table, so the check reads their
effect: the records the run created under a key must number exactly one per key. The expected counts come from
``results/<run>/ledger.json``, which the Locust run wrote (with the counters of the stub providers).

A dead-lettered job is a violation: the stub providers answer thumbnails, geocoding and Strava, so nothing should
give up. ``--fault`` is for a run that injected a fault on purpose; it reports dead-letters and failed refresh
attempts instead of failing on them.
"""

import argparse
import json
import os
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

import psycopg
from psycopg import sql

HERE = Path(__file__).resolve().parent
#: The secrets ``run.sh`` makes for the stack, among them the database password.
SECRETS_FILE = HERE / ".env.secrets"


def database_url() -> str:
    """Return the stack's database URL: ``LOADTEST_DATABASE_URL``, or the published port with the stack's password."""
    if url := os.environ.get("LOADTEST_DATABASE_URL"):
        return url
    secrets = dict(
        line.split("=", 1) for line in SECRETS_FILE.read_text().splitlines() if "=" in line and not line.startswith("#")
    )
    return f"postgresql://endurain:{secrets['POSTGRES_PASSWORD']}@127.0.0.1:15432/endurain"


#: The server refuses an upload past this many open ones per user.
UPLOAD_CAP = 10
#: Seconds past its lease (or past becoming due) after which a job counts as stuck; the reaper runs every minute.
STUCK_GRACE_SECONDS = 180
#: Seconds without progress after which the drain wait gives up. A killed worker's jobs wait for the lease (45 s) and the
#: reaper (every minute) before anyone finishes one, about 105 s; 180 s covers that with margin and equals the stuck grace.
#: It is also the look-ahead: a job that becomes available within it is waited for, a later one is only reported.
STALL_SECONDS = 180.0

#: (child table, parent table, child column, parent column): rows whose parent is gone.
ORPHAN_PAIRS = (
    ("activities_streams", "activities", "activity_id", "id"),
    ("activity_laps", "activities", "activity_id", "id"),
    ("activity_sets", "activities", "activity_id", "id"),
    ("activity_workout_steps", "activities", "activity_id", "id"),
    ("activity_media", "activities", "activity_id", "id"),
    ("activities", "users", "user_id", "id"),
    ("gear", "users", "user_id", "id"),
    ("gear_components", "gear", "gear_id", "id"),
    ("health_weight", "users", "user_id", "id"),
    ("health_steps", "users", "user_id", "id"),
    ("health_sleep", "users", "user_id", "id"),
    ("health_water", "users", "user_id", "id"),
    ("notifications", "users", "user_id", "id"),
    ("activity_ingestion_jobs", "users", "user_id", "id"),
)


#: The durable events of the jobs the lifecycle scenario starts: a profile export, a gear deletion, an account deletion.
LIFECYCLE_EVENTS = ("users.profile_export_requested", "gears.deletion_requested", "users.deletion_requested")


class Report:
    """The rows of the result table."""

    def __init__(self) -> None:
        self.rows: list[dict[str, str]] = []

    def add(self, name: str, ok: bool | None, detail: str) -> None:
        """Record a check: ``ok`` True passes, False violates, None is information only."""
        self.rows.append(
            {"check": name, "result": "INFO" if ok is None else ("OK" if ok else "FAIL"), "detail": detail}
        )

    @property
    def failed(self) -> bool:
        return any(row["result"] == "FAIL" for row in self.rows)

    def print(self) -> None:
        width = max(len(row["check"]) for row in self.rows)
        print(f"\n{'invariant'.ljust(width)}  result  detail")
        print(f"{'-' * width}  ------  ------")
        for row in self.rows:
            print(f"{row['check'].ljust(width)}  {row['result']:<6}  {row['detail']}")


def scalar(cur: psycopg.Cursor, sql: str, *params):
    cur.execute(sql, params)
    return cur.fetchone()[0]


def referencing_columns(cur: psycopg.Cursor, table: str) -> list[tuple[str, str]]:
    """Return ``(table, column)`` of every foreign key that points at ``table``, from the catalog."""
    cur.execute(
        "SELECT (SELECT relname FROM pg_class WHERE oid = c.conrelid), a.attname FROM pg_constraint c "
        "JOIN pg_attribute a ON a.attrelid = c.conrelid AND a.attnum = ANY (c.conkey) "
        "WHERE c.contype = 'f' AND c.confrelid = %s::regclass ORDER BY 1, 2",
        (table,),
    )
    return cur.fetchall()


def rows_naming(cur: psycopg.Cursor, table: str, column: str, ids: list[str]) -> int:
    """Count the rows of ``table`` whose ``column`` is one of ``ids``."""
    if not ids:
        return 0
    query = sql.SQL("SELECT count(*) FROM {} WHERE {} = ANY(%s::uuid[])").format(
        sql.Identifier(table), sql.Identifier(column)
    )
    return scalar(cur, query, ids)


def check_lifecycles(cur: psycopg.Cursor, report: Report, cycles: list[dict]) -> None:
    """Check what the lifecycle scenario's accounts left in the database: exports, gear deletions, account deletions.

    The ledger says which jobs were accepted; the database says whether the work was done, whatever the client saw
    (a cycle cut off by the end of the run asked for its jobs all the same).

    Args:
        cur: A cursor on the stack's database.
        report: Where the checks go.
        cycles: ``ledger["lifecycles"]``.
    """
    user_ids = [c["user_id"] for c in cycles]
    alive = {row[0] for row in cur.execute("SELECT id::text FROM users WHERE id = ANY(%s::uuid[])", (user_ids,))}
    report.add(
        "lifecycle accounts",
        None,
        f"{len(cycles)} created by an administrator, {len(alive)} still exist; plans: "
        + ", ".join(
            f"{name} {sum(1 for c in cycles if c['plan'].get(name) == value)}"
            for name, value in (("export", True), ("strava", True), ("end", "keep"), ("end", "admin"), ("end", "self"))
        ),
    )

    # -- exports ---------------------------------------------------------------------------------------------------
    exports = [c["export"] for c in cycles if c["export"] and c["export"]["job_id"]]
    failed = [e["job_id"] for e in exports if e["status"] == "failed"]
    bad = [f"{e['job_id']}: {e['archive']}" for e in exports if e["status"] == "succeeded" and e["archive"] != "ok"]
    open_exports = sum(1 for e in exports if e["status"] not in ("succeeded", "failed"))
    report.add(
        "every export succeeded and its archive was a valid ZIP of the account's data",
        not failed and not bad,
        f"{len(exports)} exports, {len(failed)} failed, {len(bad)} bad archives"
        + (f" ({bad[0]})" if bad else "")
        + (f", {open_exports} not read to the end when the run stopped" if open_exports else ""),
    )

    # -- gear deletions --------------------------------------------------------------------------------------------
    gears = [(c, c["gear"]) for c in cycles if c["gear"] and c["gear"]["job_id"]]
    gear_ids = [g["id"] for _, g in gears]
    still_there = rows_naming(cur, "gear", "id", gear_ids)
    client_problems = [g["id"] for _, g in gears if g["status"] == "failed" or g.get("gone") is False]
    client_problems += [g["id"] for _, g in gears if g.get("unassigned") is False]
    # An account that still exists keeps its activities and the sync tombstone of the gear; one deleted has neither.
    kept = [(c, g) for c, g in gears if c["user_id"] in alive]
    kept_activities = [a for _, g in kept for a in g["activity_ids"]]
    activities_stored = rows_naming(cur, "activities", "id", kept_activities)
    still_assigned = (
        scalar(
            cur,
            "SELECT count(*) FROM activities WHERE id = ANY(%s::uuid[]) AND gear_id = ANY(%s::uuid[])",
            kept_activities,
            gear_ids,
        )
        if kept_activities
        else 0
    )
    tombstones = rows_naming(cur, "gear_deletions", "record_id", [g["id"] for _, g in kept])
    report.add(
        "deleted gears are gone, their activities kept and no longer assigned",
        still_there == 0
        and not client_problems
        and activities_stored == len(kept_activities)
        and still_assigned == 0
        and tombstones == len(kept),
        f"{len(gears)} deletions accepted: {still_there} gears left; accounts kept: {activities_stored}/"
        f"{len(kept_activities)} activities stored, {still_assigned} still assigned, {tombstones}/{len(kept)} "
        f"tombstones; the client saw {len(client_problems)} problems",
    )

    # -- strava unlinks --------------------------------------------------------------------------------------------
    unlinked = [c for c in cycles if c["strava"] and c["strava"].get("unlink") == "succeeded" and c["user_id"] in alive]
    ids = [c["user_id"] for c in unlinked]
    leftover_activities = (
        scalar(
            cur,
            "SELECT count(*) FROM activity_sources WHERE user_id = ANY(%s::uuid[]) AND kind = 'strava'",
            ids,
        )
        if ids
        else 0
    )
    leftover_gear = (
        scalar(cur, "SELECT count(*) FROM gear WHERE user_id = ANY(%s::uuid[]) AND strava_gear_id IS NOT NULL", ids)
        if ids
        else 0
    )
    still_linked = (
        scalar(
            cur,
            "SELECT count(*) FROM users_integrations WHERE user_id = ANY(%s::uuid[]) "
            "AND (strava_token IS NOT NULL OR strava_refresh_token IS NOT NULL)",
            ids,
        )
        if ids
        else 0
    )
    strava = [c["strava"] for c in cycles if c["strava"]]
    outcomes: dict[str, int] = {}
    for entry in strava:
        outcome = entry.get("outcome", "not finished")
        outcomes[outcome] = outcomes.get(outcome, 0) + 1
    report.add(
        "strava unlink leaves no imported activity or gear and no token",
        leftover_activities == 0 and leftover_gear == 0 and still_linked == 0,
        f"{len(unlinked)} unlinked accounts kept: {leftover_activities} strava activities, {leftover_gear} strava "
        f"gears, {still_linked} still linked; {sum(e.get('imported', 0) for e in strava)} activities imported in all; "
        f"cycle outcomes {outcomes or 'none'}",
    )

    # -- account deletions -----------------------------------------------------------------------------------------
    deleted = [c for c in cycles if c["deletion"] and c["deletion"]["job_id"]]
    left = [c["user_id"] for c in deleted if c["user_id"] in alive]
    targets = (
        ("users", [c["user_id"] for c in deleted]),
        ("activities", [a for c in deleted for a in c["activity_ids"]]),
        ("gear", [c["gear"]["id"] for c in deleted if c["gear"]]),
    )
    leftovers = []
    tables = set()
    for table, ids_ in targets:
        for child, column in referencing_columns(cur, table):
            tables.add(child)
            if count := rows_naming(cur, child, column, ids_):
                leftovers.append(f"{child}.{column}: {count}")
    report.add(
        "deleted accounts leave no row behind in the tables that reference them",
        not left and not leftovers and not any(c["deletion"]["status"] == "failed" for c in deleted),
        f"{len(deleted)} deletions accepted ({sum(1 for c in deleted if c['deletion']['by'] == 'self')} by the user), "
        f"{len(left)} users left; {len(tables)} tables checked; " + ("; ".join(leftovers[:5]) or "no leftover rows"),
    )

    # -- the jobs --------------------------------------------------------------------------------------------------
    cur.execute(
        "SELECT event_type, status, count(*) FROM jasil_processing_jobs WHERE event_type = ANY(%s) GROUP BY 1, 2 "
        "ORDER BY 1, 2",
        (list(LIFECYCLE_EVENTS),),
    )
    jobs = cur.fetchall()
    unfinished = sum(n for _, status, n in jobs if status in ("pending", "claimed", "dead_letter"))
    report.add(
        "every export and deletion job ended in the database",
        unfinished == 0,
        "; ".join(f"{event} {status}={n}" for event, status, n in jobs) or "no such jobs",
    )


def wait_for_drain(cur: psycopg.Cursor, report: Report, stall: float) -> None:
    """Wait while due work makes progress; stop when none is left or none has been done for ``stall`` seconds.

    Work is a durable job that is claimed or pending and available within ``stall`` seconds, an ingestion job still
    open, or an outbox row not relayed. Progress is a job attempt that ended or an outbox row relayed. A job deferred
    beyond the window (a refresh waiting for a provider's rate limit) is not waited for; it is reported. A stall leaves
    its jobs open, so the stuck check below fails the ones still due past the grace.
    """
    started = last_progress = time.monotonic()
    initial: str | None = None
    progress = None
    while True:
        open_jobs = scalar(
            cur,
            "SELECT count(*) FROM jasil_processing_jobs WHERE status = 'claimed' "
            "OR (status = 'pending' AND available_at <= now() + make_interval(secs => %s))",
            stall,
        )
        unrelayed = scalar(cur, "SELECT count(*) FROM jasil_event_outbox WHERE relayed_at IS NULL")
        ingesting = scalar(
            cur,
            "SELECT count(*) FROM activity_ingestion_jobs WHERE status IN ('pending', 'processing') "
            "OR (status = 'deferred' AND (retry_after IS NULL OR retry_after <= now() + make_interval(secs => %s)))",
            stall,
        )
        now = time.monotonic()
        if initial is None:
            initial = f"{open_jobs} jobs, {ingesting} ingestion jobs, {unrelayed} unrelayed events"
        cur.execute(
            "SELECT (SELECT count(*) FROM jasil_job_attempts WHERE outcome IS NOT NULL), "
            "(SELECT count(*) FROM jasil_event_outbox WHERE relayed_at IS NOT NULL)"
        )
        done = cur.fetchone()
        if done != progress:
            progress, last_progress = done, now
        if open_jobs == 0 and unrelayed == 0 and ingesting == 0:
            verdict = "drained"
            break
        if now - last_progress > stall:
            verdict = (
                f"stalled (no progress for {stall:.0f}s; {open_jobs} jobs, {ingesting} ingestion jobs, "
                f"{unrelayed} unrelayed events left)"
            )
            break
        time.sleep(2)
        cur.connection.rollback()  # a fresh snapshot for the next look
    report.add("drain began with", None, initial)
    report.add("queues drained", None, f"{verdict} after {time.monotonic() - started:.0f}s")
    cur.execute(
        "SELECT subscriber_id, count(*), max(available_at) FROM jasil_processing_jobs "
        "WHERE status = 'pending' AND available_at > now() + make_interval(secs => %s) GROUP BY 1 ORDER BY 1",
        (stall,),
    )
    deferred = cur.fetchall()
    report.add(
        "jobs deferred beyond the stall window (not waited for)",
        None,
        "; ".join(f"{s}={n} until {latest:%H:%M:%S}" for s, n, latest in deferred) or "none",
    )


def check(
    url: str, run: str, results: Path, stall_timeout: float, *, fault: bool = False, since: datetime | None = None
) -> Report:
    report = Report()
    ledger_file = results / run / "ledger.json"
    ledger = json.loads(ledger_file.read_text()) if ledger_file.exists() else {}
    with psycopg.connect(url) as conn:
        conn.read_only = True
        with conn.cursor() as cur:
            wait_for_drain(cur, report, stall_timeout)
            conn.rollback()

            # -- duplicates ------------------------------------------------------------------------------------------------
            cur.execute(
                "SELECT user_id, kind, provider_id::text, count(*) FROM activity_sources WHERE provider_id IS NOT NULL "
                "GROUP BY user_id, kind, provider_id, session_start HAVING count(*) > 1 "
                "UNION ALL SELECT user_id, 'file', file_sha256, count(*) FROM activity_sources "
                "WHERE file_sha256 IS NOT NULL GROUP BY user_id, file_sha256, session_start HAVING count(*) > 1 LIMIT 5"
            )
            duplicates = cur.fetchall()
            report.add(
                "no duplicate activity per (user, provider id / file hash)",
                not duplicates,
                f"{len(duplicates)} duplicated",
            )

            # -- idempotency -----------------------------------------------------------------------------------------------
            bad_keys = []
            created_keys = 0
            for entry in ledger.get("gears", []):
                found = scalar(
                    cur,
                    "SELECT count(*) FROM gear WHERE user_id = %s AND nickname = %s",
                    entry["user_id"],
                    entry["nickname"],
                )
                if any(status == 201 for status in entry["statuses"]):
                    created_keys += 1
                    if found != 1:
                        bad_keys.append(f"{entry['key']}: {found} gears, statuses {entry['statuses']}")
                elif found > 1:
                    bad_keys.append(f"{entry['key']}: {found} gears, statuses {entry['statuses']}")
            report.add(
                "one gear per Idempotency-Key (concurrent same-key creates)",
                not bad_keys,
                f"{len(ledger.get('gears', []))} keys fired, {created_keys} created; "
                + ("; ".join(bad_keys[:3]) or "all exactly 1"),
            )
            upload_key_problems = []
            for entry in ledger.get("uploads", []):
                found = scalar(
                    cur,
                    "SELECT count(*) FROM activity_ingestion_jobs WHERE user_id = %s AND kind = 'upload' "
                    "AND idempotency_key IN (%s, %s)",
                    entry["user_id"],
                    entry["key"],
                    entry["key"].strip('"'),
                )
                if found != 1:
                    upload_key_problems.append(f"{entry['key']}: {found} jobs")
            report.add(
                "one upload job per Idempotency-Key",
                not upload_key_problems and not ledger.get("upload_key_violations"),
                f"{len(ledger.get('uploads', []))} keys; "
                + ("; ".join(upload_key_problems[:3]) or "all exactly 1")
                + (
                    f"; replays answered another job: {ledger['upload_key_violations'][:2]}"
                    if ledger.get("upload_key_violations")
                    else ""
                ),
            )
            report.add(
                "idempotent replays answered the first record",
                not ledger.get("idempotency_violations"),
                f"{len(ledger.get('idempotency_violations', []))} violations",
            )

            # -- upload cap ------------------------------------------------------------------------------------------------
            cur.execute(
                """
                WITH ev AS (
                    SELECT user_id, created_at AS t, 1 AS d FROM activity_ingestion_jobs WHERE kind = 'upload'
                    UNION ALL
                    SELECT user_id, completed_at, -1 FROM activity_ingestion_jobs
                    WHERE kind = 'upload' AND completed_at IS NOT NULL
                ), running AS (
                    SELECT user_id, sum(d) OVER (PARTITION BY user_id ORDER BY t, d) AS open_uploads FROM ev
                )
                SELECT coalesce(max(open_uploads), 0), count(DISTINCT user_id) FROM running
                """
            )
            # The timeline of every upload job is the cap itself; counting a burst's acceptances is not, since uploads
            # of a slow burst complete before its last ones arrive.
            peak, users = cur.fetchone()
            report.add(
                "open uploads per user never above the cap",
                peak <= UPLOAD_CAP,
                f"peak {peak} open (cap {UPLOAD_CAP}), {users} users uploaded",
            )

            # -- jobs ------------------------------------------------------------------------------------------------------
            stuck = scalar(
                cur,
                "SELECT count(*) FROM jasil_processing_jobs WHERE "
                "(status = 'claimed' AND lease_expires_at < now() - make_interval(secs => %s)) "
                "OR (status = 'pending' AND available_at < now() - make_interval(secs => %s))",
                STUCK_GRACE_SECONDS,
                STUCK_GRACE_SECONDS,
            )
            open_jobs = scalar(cur, "SELECT count(*) FROM jasil_processing_jobs WHERE status IN ('pending', 'claimed')")
            report.add("no durable job stuck past its lease", stuck == 0, f"{stuck} stuck, {open_jobs} still open")
            stuck_ingestion = scalar(
                cur,
                "SELECT count(*) FROM activity_ingestion_jobs WHERE status IN ('pending', 'processing') "
                "AND updated_at < now() - make_interval(secs => %s)",
                STUCK_GRACE_SECONDS,
            )
            report.add("no ingestion job stuck pending/processing", stuck_ingestion == 0, f"{stuck_ingestion} stuck")
            cur.execute(
                "SELECT job_id, count(*) FILTER (WHERE outcome = 'completed') AS done, "
                "count(*) FILTER (WHERE outcome = 'superseded') AS superseded FROM jasil_job_attempts "
                "GROUP BY job_id HAVING count(*) FILTER (WHERE outcome = 'completed') > 1 "
                "OR count(*) FILTER (WHERE outcome = 'superseded') > 0 LIMIT 5"
            )
            twice = cur.fetchall()
            report.add("no job run twice (two completions or a superseded attempt)", not twice, f"{len(twice)} jobs")
            cur.execute("SELECT outcome, count(*) FROM jasil_job_attempts GROUP BY 1 ORDER BY 2 DESC")
            report.add("attempt outcomes", None, ", ".join(f"{o or 'open'}={n}" for o, n in cur.fetchall()) or "none")
            # Dead-letters since the run started: a stack that several runs share keeps the earlier ones' rows.
            floor = since or datetime.fromtimestamp(0, UTC)
            cur.execute(
                "SELECT subscriber_id, count(*) FROM jasil_processing_jobs "
                "WHERE status = 'dead_letter' AND created_at >= %s GROUP BY 1",
                (floor,),
            )
            by_subscriber = cur.fetchall()
            dead = sum(n for _, n in by_subscriber)
            report.add(
                "no dead-lettered job" if not fault else "dead-letter jobs (a fault was injected: reported)",
                None if fault else dead == 0,
                f"{dead}" + ("".join(f"; {s}={n}" for s, n in by_subscriber)),
            )

            # -- strava (the stub provider) ----------------------------------------------------------------------
            refresh = dict(
                cur.execute(
                    "SELECT status, count(*) FROM activity_ingestion_jobs WHERE kind = 'refresh' AND created_at >= %s GROUP BY 1",
                    (floor,),
                ).fetchall()
            )
            served = ledger.get("stub", {}).get("served", {})
            limited = served.get("strava_429", 0)
            report.add(
                "strava refresh jobs",
                None,
                ", ".join(f"{k}={v}" for k, v in sorted(refresh.items()))
                + f"; stub served {served.get('strava_activities', 0)} activity lists, {served.get('strava_activity', 0)} "
                f"activities, {limited} answers of 429",
            )
            if refresh or limited:
                failed_refresh = refresh.get("failed", 0)
                report.add(
                    "no strava refresh job failed",
                    None if fault else failed_refresh == 0,
                    f"{failed_refresh} failed" + (" (a fault was injected: reported)" if fault else ""),
                )
                unset = scalar(
                    cur,
                    "SELECT count(*) FROM activity_ingestion_jobs WHERE status = 'deferred' AND retry_after IS NULL",
                )
                report.add(
                    "every deferred refresh says when it runs again (retry_after)", unset == 0, f"{unset} without"
                )
                # A 429 defers the refresh: not failed, not retried into the limit, so no attempt ends failed. (An attempt a
                # crash cut short ends ``lease_expired``, which is not a failure of the provider call.)
                cur.execute(
                    "SELECT j.event_type, count(DISTINCT j.id), count(*) FILTER (WHERE a.outcome = 'failed'), "
                    "count(DISTINCT j.id) FILTER (WHERE j.status = 'dead_letter') "
                    "FROM jasil_processing_jobs j LEFT JOIN jasil_job_attempts a ON a.job_id = j.id "
                    "WHERE j.event_type LIKE '%%refresh%%' AND j.created_at >= %s GROUP BY 1",
                    (floor,),
                )
                durable = cur.fetchall()
                report.add(
                    "refresh jobs ended no attempt failed (a deferral is not a failure and uses no retry)",
                    None
                    if fault
                    else all(failed_attempts == 0 and dead_jobs == 0 for _, _, failed_attempts, dead_jobs in durable),
                    "; ".join(f"{event}: {n} jobs, {f} failed attempts, {d} dead" for event, n, f, d in durable)
                    or "none",
                )
            if limited:
                # A deferral ends the refresh's durable job and the redispatch queues another for the same row, so a
                # refresh was deferred if it still is or has more than one durable job, however long the run went on.
                deferred = scalar(
                    cur,
                    "SELECT count(*) FROM activity_ingestion_jobs i WHERE i.kind = 'refresh' AND i.created_at >= %s "
                    "AND (i.status = 'deferred' OR (SELECT count(*) FROM jasil_processing_jobs j "
                    "WHERE j.event_type = 'activity.refresh_requested' AND j.payload->>'job_id' = i.id::text) > 1)",
                    floor,
                )
                report.add(
                    "429 from strava deferred refreshes",
                    deferred > 0,
                    f"{deferred} deferred after {limited} answers of 429",
                )
            strava_activities = scalar(cur, "SELECT count(*) FROM activity_sources WHERE kind = 'strava'")
            report.add(
                "activities stored from strava (no duplicate per strava id: checked above)",
                None,
                f"{strava_activities}",
            )

            # -- outbox ----------------------------------------------------------------------------------------------------
            unrelayed = scalar(cur, "SELECT count(*) FROM jasil_event_outbox WHERE relayed_at IS NULL")
            total = scalar(cur, "SELECT count(*) FROM jasil_event_outbox")
            report.add("outbox drained", unrelayed == 0, f"{unrelayed} of {total} events not relayed")

            # -- orphans ---------------------------------------------------------------------------------------------------
            orphans = []
            for child, parent, child_col, parent_col in ORPHAN_PAIRS:
                count = scalar(
                    cur,
                    f"SELECT count(*) FROM {child} c WHERE c.{child_col} IS NOT NULL AND NOT EXISTS "
                    f"(SELECT 1 FROM {parent} p WHERE p.{parent_col} = c.{child_col})",
                )
                if count:
                    orphans.append(f"{child}->{parent}: {count}")
            report.add("no orphan rows", not orphans, "; ".join(orphans) or f"{len(ORPHAN_PAIRS)} parent links checked")

            # -- counts match the run --------------------------------------------------------------------------------------
            steps = ledger.get("steps", [])
            found = (
                scalar(cur, "SELECT count(*) FROM health_steps WHERE id = ANY(%s::uuid[])", [s["id"] for s in steps])
                if steps
                else 0
            )
            report.add(
                "steps created by the run are all stored", found == len(steps), f"ledger {len(steps)}, database {found}"
            )
            weights = ledger.get("weights", [])
            # A weight whose DELETE had no answer, or a 5xx, may be either; only known outcomes are checked.
            kept = [w["id"] for w in weights if w["deleted"] is False]
            gone = [w["id"] for w in weights if w["deleted"] is True]
            unknown = len(weights) - len(kept) - len(gone)
            kept_found = (
                scalar(cur, "SELECT count(*) FROM health_weight WHERE id = ANY(%s::uuid[])", kept) if kept else 0
            )
            gone_found = (
                scalar(cur, "SELECT count(*) FROM health_weight WHERE id = ANY(%s::uuid[])", gone) if gone else 0
            )
            report.add(
                "weights: kept stored, deleted gone",
                kept_found == len(kept) and gone_found == 0,
                f"kept {kept_found}/{len(kept)}, deleted still present {gone_found}/{len(gone)}, outcome unknown {unknown}",
            )
            uploads = ledger.get("uploads", [])
            succeeded = [u for u in uploads if u["status"] == "succeeded"]
            failed = [u for u in uploads if u["status"] == "failed"]
            unfinished = [u for u in uploads if u["status"] not in ("succeeded", "failed")]
            ids = [a for u in succeeded for a in u["activity_ids"]]
            activities = scalar(cur, "SELECT count(*) FROM activities WHERE id = ANY(%s::uuid[])", ids) if ids else 0
            report.add(
                "uploads: one stored activity per succeeded job",
                len(ids) == len(succeeded) and activities == len(ids) and not failed,
                f"{len(uploads)} accepted, {len(succeeded)} succeeded, {len(failed)} failed, {len(unfinished)} unfinished; "
                f"{len(ids)} activity ids reported, {activities} stored",
            )
            # What the database says, whatever the client saw: every upload job of the run ends, and ends once.
            cur.execute(
                "SELECT status, count(*) FROM activity_ingestion_jobs WHERE kind = 'upload' AND filename LIKE %s GROUP BY 1",
                (f"load-{run}-%",),
            )
            states = dict(cur.fetchall())
            in_database = sum(states.values())
            open_uploads = sum(n for status, n in states.items() if status not in ("completed", "failed"))
            report.add(
                "every upload job of the run ended in the database",
                open_uploads == 0 and not states.get("failed"),
                f"{in_database} jobs; " + (", ".join(f"{k}={v}" for k, v in sorted(states.items())) or "none"),
            )
            # A request cut off by a fault may have created its job without the client hearing of it.
            report.add(
                "upload jobs in the database match the accepted uploads"
                if not fault
                else "upload jobs in the database cover the accepted uploads (a fault was injected)",
                in_database >= len(uploads) if fault else in_database == len(uploads),
                f"ledger {len(uploads)}, database {in_database}",
            )

            # -- lifecycle: exports and deletions --------------------------------------------------------------
            if cycles := ledger.get("lifecycles"):
                check_lifecycles(cur, report, cycles)
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--run", default="manual")
    parser.add_argument("--url", default=None, help="the database URL; by default the stack's (database_url)")
    parser.add_argument("--results", type=Path, default=Path(os.environ.get("LOADTEST_RESULTS", HERE / "results")))
    parser.add_argument(
        "--stall-timeout",
        type=float,
        default=STALL_SECONDS,
        help="seconds without a finished job attempt or relayed event after which the drain gives up",
    )
    parser.add_argument(
        "--fault", action="store_true", help="a fault was injected: report dead-letters, do not fail on them"
    )
    args = parser.parse_args()
    report = check(args.url or database_url(), args.run, args.results, args.stall_timeout, fault=args.fault)
    report.print()
    (args.results / args.run).mkdir(parents=True, exist_ok=True)
    (args.results / args.run / "invariants.json").write_text(json.dumps(report.rows, indent=2))
    print("\nINVARIANTS", "VIOLATED" if report.failed else "OK")
    return 1 if report.failed else 0


if __name__ == "__main__":
    sys.exit(main())
