# Troubleshooting

How to find out what went wrong. Start with the logs, then check background work if something derived (a thumbnail, a location, a sync) is missing.

## Find the failing request

Every API error includes a `request_id`, and the same id is in the server log (see [Errors, concurrency and rate limits](../integrate/errors-and-limits.md)). The id is also returned in the `X-Request-ID` header. Ask the user for the id from the failed response, then search the log for it.

- In Docker: `docker compose logs endurain | grep <request_id>`
- The server also writes JSON lines to `app.log` in `LOGS_DIR` (`/app/backend/logs` in the image, `/var/opt/endurain/backend/logs` on the host with the default compose file).
- Raise the detail with `LOG_LEVEL=debug` (or `trace`) and restart. Return it to `info` afterwards.

## Endurain does not start

Endurain refuses to start on an inconsistent configuration and names the setting at fault. Read the first error in the log. The cases are listed in [Scaling and background jobs](scaling-and-background-jobs.md#startup-validation); the common ones are:

- `WEB_WORKERS` above 1, or `DEPLOYMENT_PROFILE=distributed`, without Redis for state and events.
- `distributed` with local storage.
- A job worker with `JOBS_LEASE_SECONDS` below 45.

A missing `SECRET_KEY` or `FERNET_KEY`, or a non-positive token lifetime, also stops the start.

## You cannot sign in

- **After the first start:** the `ENDURAIN_HOST` value must match the URL you open, including `https` once a reverse proxy is in place. See [Quick start](quick-start.md#visit-the-site).
- **Behind a reverse proxy:** set `BEHIND_PROXY=true`, otherwise client addresses and secure cookies are wrong.
- **Single sign-on problems:** see the troubleshooting section of [Single Sign-On](../features/single-sign-on.md).
- **Too many attempts:** after repeated failures an account or address is locked out for a while, and the API answers `429` with a `Retry-After` header.

## A thumbnail, location or sync is missing

Derived work (map thumbnails, reverse geocoding, notifications, provider syncs) runs in the background. See [How events are delivered](scaling-and-background-jobs.md#how-events-are-delivered).

- **Without durable jobs (`JOBS_ENABLED=false`, the default):** a failure is logged and swallowed. A scheduled backfill repairs missing results later, so wait for it and check the log for the error.
- **With durable jobs:** inspect the job tables below. If jobs sit in `pending`, check that a worker is running, especially when `JOBS_RUN_IN_PROCESS_WORKER=false`.

A worker that was killed mid-job is requeued after its lease expires, so the job finishes a few minutes late instead of being lost.

## Inspect background jobs (durable jobs only)

The job state is in PostgreSQL. Connect with `psql` (or Adminer) and query it read-only.

```sql
-- How many jobs are in each state
SELECT status, count(*) FROM processing_jobs GROUP BY status;

-- Jobs that gave up, newest first
SELECT subscriber_id, event_type, attempts, last_error, updated_at
FROM processing_jobs
WHERE status = 'dead_letter'
ORDER BY updated_at DESC
LIMIT 20;
```

`processing_jobs.status` is `pending`, `claimed`, `completed` or `dead_letter`. A failed job returns to `pending` with a later `available_at` (exponential backoff) until `attempts` reaches the maximum (`JOBS_MAX_ATTEMPTS`), then it becomes `dead_letter`. `last_error` holds the most recent failure.

Dead-lettered jobs are kept for review and never pruned automatically. For derived work the scheduled backfills repair the result anyway. An upload or provider refresh that dead-lettered is a command the user can simply start again.

## Follow one event

When `EVENT_LOG_ENABLED=true` (the default), each event's lifecycle is recorded in `event_log`:

```sql
SELECT event_type, status, handler_name, retry_count, error_message, created_at
FROM event_log
WHERE event_metadata ->> 'request_id' = '<request_id>'
ORDER BY created_at;
```

Statuses are `published`, `queued`, `processing`, `completed`, `failed` and `dead_letter`. Rows older than `EVENT_LOG_RETENTION_DAYS` (90) are pruned.

## Importing problems

- A file that failed in a bulk import is counted as failed and its bytes are kept in the `bulk_import_errors` storage area. See [Importing data](../features/importing.md).
- An import that never finishes is closed by a reaper after 24 hours, and staged uploads nobody references are removed after 2 days.
- A profile import is limited by available memory. See [Exporting and importing your data](../features/export-import.md#limits).

## Database connections

Each web process keeps up to 60 database connections. If requests time out waiting for a connection, the total across processes is probably above PostgreSQL's `max_connections`. See [Sizing](scaling-and-background-jobs.md#sizing).

## Still stuck

Open an issue on [GitHub](https://github.com/endurain-project/endurain/issues) with the Endurain version, your deployment shape, the relevant log lines (with secrets removed) and the `request_id` if you have one.
