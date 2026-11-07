# Reviewing for horizontal scaling

Replicas share no process state; the deployment shapes are in `docs/getting-started/scaling-and-background-jobs.md`.
Storage, events, jobs, schedules and nets are covered in `platform-jasil.md`; this checklist covers what that file does not.

## Checklist

| Look for | Why it breaks | Use instead |
| --- | --- | --- |
| Module-level dicts, `lru_cache` or singletons holding rate limits, lockout, MFA, OAuth state or WebSocket tickets | Another replica never sees it | The platform `state` capability |
| `BackgroundTasks` for work that must not be lost | Dropped on restart or replica loss | A published event with a durable subscriber and net |
| `asyncio.to_thread`, `run_in_executor` or `future.result(timeout=N)` on a request path for long work | Exhausts the pool, ties up the request | A job; keep calls short |
| A critical flow whose only delivery path is a WebSocket message | Lost when the socket or replica changes | A pollable status endpoint; WebSocket is an optimization |
| Tokens or API keys in URLs or query parameters | Leak into logs and history | Headers or the one-time ticket in `modules/websocket/ticket_store.py` |
| A provider call that fails on a rate limit as an ordinary error | Retries burn attempts into the same limit on every replica | `TooManyRequestsError(retry_at=...)`; the ingestion job defers |
| A database session held open across a provider or network call | Pins a pool connection for the length of the round trip | Short sessions before and after the call |
| `len(query.all())` for a count | Loads every row | `select(func.count())` |
| Unbounded work per request or per user (no size, page or job cap) | One caller can starve every replica | Limits in `security.md` (Abuse and resource limits) |
| Frontend `socket.onmessage = fn` | Components overwrite each other | `addEventListener('message', fn)` |

## Reporting

Review the code or diff against every row and report:

1. Findings: severity (critical blocks scaling or zero-downtime deploys, moderate affects UX or operations, low is worth fixing), `file:line`, current behavior, why it fails with several replicas, fix.
2. Rows checked and clear, so coverage is visible.
