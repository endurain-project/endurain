"""Scheduled retention pruning for the substrate's append-only bookkeeping tables.

The event_log (F7) and durable-job (F8) tables are append-only: every event
writes an ``event_log`` row, the relay stamps ``event_outbox`` rows, and each
``(event, subscriber)`` pair produces a ``processing_jobs`` row. Left alone they
grow without bound — and activities, the highest-volume event producer, fill them
fastest. This module prunes rows past their retention window on a schedule
(``EVENT_LOG_RETENTION_DAYS`` for the event_log trail, ``JOBS_RETENTION_DAYS`` for
the durable-job tables — each configured and disabled independently), deleting
only what is safe to lose:

* every ``event_log`` row (best-effort, safe-to-lose observability trail),
* relayed ``event_outbox`` rows (already fanned out into jobs), and
* ``completed`` ``processing_jobs`` rows.

In-flight and human-actionable rows are never touched: unrelayed outbox rows
(pending relay), ``pending`` / ``claimed`` jobs (in-flight work), and
``dead_letter`` jobs (kept for operator review). It runs single-runner across
replicas via the platform ``LockProvider`` and is inert when both windows are
``<= 0`` (retention disabled — keep every row forever).
"""

from datetime import datetime, timedelta

import core.config as core_config
import core.database as core_database
import core.logger as core_logger
import infra.event_log.crud as event_log_crud
import infra.jobs.crud as jobs_crud
import infra.jobs.outbox as jobs_outbox
import infra.runtime as platform_runtime

logger = core_logger.get_logger(__name__)

# Single-runner lock name: the deletes are idempotent, but the lock keeps the
# work from being duplicated across replicas.
_PRUNE_LOCK_NAME = "platform_retention_prune"


def prune_expired_records() -> None:
    """Prune substrate bookkeeping rows older than their retention windows.

    Scheduled daily (and once at startup). Each window is applied independently:
    ``EVENT_LOG_RETENTION_DAYS`` gates the event_log trail and
    ``JOBS_RETENTION_DAYS`` gates the durable-job tables. No-ops when both are
    disabled (``<= 0``) or when another replica already holds the prune lock.

    Returns:
        None.
    """
    event_log_days = core_config.settings.EVENT_LOG_RETENTION_DAYS
    jobs_days = core_config.settings.JOBS_RETENTION_DAYS
    if event_log_days <= 0 and jobs_days <= 0:
        return

    platform = platform_runtime.get_active_platform()
    with platform.lock.try_acquire(_PRUNE_LOCK_NAME) as acquired:
        if not acquired:
            logger.debug("Retention prune: another replica holds the lock; skipping")
            return
        _run_prune(platform.clock.now(), event_log_days, jobs_days)


def _run_prune(now: datetime, event_log_days: int, jobs_days: int) -> None:
    """Delete prunable rows older than each table's window.

    Each table is pruned on its own short-lived session so one table's failure
    cannot roll back another's progress. A window of ``<= 0`` skips that group.

    Args:
        now: The current instant; each cutoff is ``now`` minus that table's window.
        event_log_days: Retention window for the event_log trail (days).
        jobs_days: Retention window for the durable-job tables (days).

    Returns:
        None.
    """
    events = outbox = jobs = 0

    if event_log_days > 0:
        cutoff = now - timedelta(days=event_log_days)
        with core_database.SessionLocal() as db:
            events = event_log_crud.delete_events_before(cutoff, db=db)

    if jobs_days > 0:
        cutoff = now - timedelta(days=jobs_days)
        with core_database.SessionLocal() as db:
            outbox = jobs_outbox.delete_relayed_before(cutoff, db=db)
        with core_database.SessionLocal() as db:
            jobs = jobs_crud.delete_completed_jobs_before(cutoff, db=db)

    if events or outbox or jobs:
        logger.info(
            f"Retention prune: deleted {events} event_log, {outbox} relayed outbox, and {jobs} completed job row(s)"
        )
    else:
        logger.debug("Retention prune: nothing to delete")
