"""The job runner — claims durable jobs and executes their subscribers.

Records outcomes to ``processing_jobs`` only (the per-subscriber execution
state), never to ``event_log`` (which stays a one-row-per-event publication
log). A successful run marks the job ``completed``; a failure reschedules it
with backoff, or dead-letters it once the attempt ceiling is reached.
"""

import logging
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy.orm import Session

import core.logger as core_logger
import infra.jobs.crud as jobs_crud
from infra.events import Event
from infra.jobs.models import ProcessingJob
from infra.jobs.registry import JobHandlerRegistry
from infra.providers import ClockProvider

logger = core_logger.get_logger(__name__)


@dataclass(frozen=True)
class ClaimedJob:
    """A detached snapshot of a claimed job, safe to use after its session closes.

    Attributes:
        id: The job id.
        event_id: The originating envelope event_id.
        event_type: The domain-event channel.
        subscriber_id: The durable subscriber to run.
        source: Where the originating event came from.
        payload: The domain payload.
        metadata: Correlation context, if any.
        attempts: The attempt number this run represents.
        timestamp: ISO-8601 enqueue time, used to rebuild the event envelope.
    """

    id: str
    event_id: str
    event_type: str
    subscriber_id: str
    source: str
    payload: dict
    metadata: dict | None
    attempts: int
    timestamp: str


class JobRunner:
    """Claims a batch of due jobs and runs each one's registered subscriber."""

    def __init__(
        self,
        *,
        registry: JobHandlerRegistry,
        clock: ClockProvider,
        session_factory: Callable[[], Session],
        worker_id: str,
        lease_seconds: int,
        batch_size: int,
        backoff_base_seconds: float,
        backoff_max_seconds: float,
    ) -> None:
        self._registry = registry
        self._clock = clock
        self._session_factory = session_factory
        self._worker_id = worker_id
        self._lease_seconds = lease_seconds
        self._batch_size = batch_size
        self._backoff_base_seconds = backoff_base_seconds
        self._backoff_max_seconds = backoff_max_seconds

    def run_once(self) -> int:
        """
        Claim and process one batch of due jobs.

        Returns:
            The number of jobs processed in this batch (0 when none were due).
        """
        now = self._clock.now()
        with self._session_factory() as db:
            claimed = jobs_crud.claim_jobs(
                worker_id=self._worker_id,
                limit=self._batch_size,
                lease_seconds=self._lease_seconds,
                now=now,
                db=db,
            )
            snapshots = [self._snapshot(job) for job in claimed]
        for snapshot in snapshots:
            # A DB error finishing one job must not abort the rest of the batch;
            # its lease simply expires and the reaper requeues it.
            try:
                self._run_job(snapshot)
            except Exception as error:
                logger.error(f"Durable job {snapshot.id} could not be finalized", exc_info=error)
        return len(snapshots)

    def reap_once(self) -> int:
        """
        Requeue (or dead-letter) jobs whose lease expired.

        Returns:
            The number of jobs reclaimed.
        """
        now = self._clock.now()
        with self._session_factory() as db:
            return jobs_crud.reclaim_expired_leases(now=now, db=db)

    def _run_job(self, job: ClaimedJob) -> None:
        handler = self._registry.get(job.subscriber_id)
        event = self._event_from(job)
        try:
            if handler is None:
                raise LookupError(f"no durable handler registered for subscriber_id {job.subscriber_id!r}")
            handler(event)
        except Exception as error:
            self._fail(job, error)
            return
        now = self._clock.now()
        with self._session_factory() as db:
            jobs_crud.mark_job_completed(job.id, now=now, db=db)

    def _fail(self, job: ClaimedJob, error: Exception) -> None:
        now = self._clock.now()
        with self._session_factory() as db:
            status = jobs_crud.mark_job_failed(
                job.id,
                str(error),
                base_seconds=self._backoff_base_seconds,
                max_seconds=self._backoff_max_seconds,
                now=now,
                db=db,
            )
        level = logging.ERROR if status == jobs_crud.STATUS_DEAD_LETTER else logging.WARNING
        logger.log(level, f"Durable job {job.id} ({job.subscriber_id}) failed -> {status or 'unknown'}", exc_info=error)

    def _event_from(self, job: ClaimedJob) -> Event:
        return Event(
            event_id=job.event_id,
            event_type=job.event_type,
            source=job.source,
            timestamp=job.timestamp,
            payload=job.payload,
            metadata=job.metadata or {},
            retry_count=job.attempts,
        )

    def _snapshot(self, job: ProcessingJob) -> ClaimedJob:
        return ClaimedJob(
            id=job.id,
            event_id=job.event_id,
            event_type=job.event_type,
            subscriber_id=job.subscriber_id,
            source=job.source,
            payload=dict(job.payload),
            metadata=dict(job.job_metadata) if job.job_metadata else None,
            attempts=job.attempts,
            timestamp=_iso(job.created_at),
        )


def _iso(moment: datetime) -> str:
    """Render an enqueue timestamp as ISO-8601 UTC (SQLite returns naive datetimes)."""
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=UTC)
    return moment.isoformat()
