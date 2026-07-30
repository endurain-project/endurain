"""Durable job queue — Postgres is the source of truth for derived work.

Each unit of derived work (one subscriber reacting to one event) is a row in the
``processing_jobs`` table. A worker claims pending rows with a lease, runs the
subscriber, and on failure reschedules with backoff until a maximum attempt
count, after which the row is dead-lettered. Because the row — not a Redis
stream entry — is the truth, retries are naturally per-subscriber and the
``(event_id, subscriber_id)`` uniqueness doubles as the idempotent-consumer
marker (enqueuing the same work twice is a no-op).
"""
