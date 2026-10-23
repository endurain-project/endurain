"""Queue Garmin Connect gear and health syncs so they never run on an API thread.

On the durable profile (``JOBS_ENABLED``) the request stages a ``garmin.sync_requested`` event
and a worker runs it, surviving a restart. Otherwise the same body runs on a small in-process
pool that is not the request threadpool.
"""

import contextvars
from concurrent.futures import Future, ThreadPoolExecutor
from datetime import date, timedelta

from sqlalchemy.orm import Session

import core.config as core_config
import core.exceptions as core_exceptions
import core.logger as core_logger
import modules.garmin.constants as garmin_constants
import modules.garmin.event_publishers as garmin_event_publishers
import modules.garmin.events as garmin_events
import modules.garmin.gear_service as garmin_gear_service
import modules.garmin.health_service as garmin_health_service
import modules.garmin.schema as garmin_schema

logger = core_logger.get_logger(__name__)

# Small on purpose: syncs are Garmin round trips and compete with the request threads.
_MAX_WORKERS = 2
_SYNC_EXECUTOR = ThreadPoolExecutor(max_workers=_MAX_WORKERS, thread_name_prefix="garmin-sync")


def shutdown_sync_executor(*, wait: bool = False) -> None:
    """Stop accepting syncs and release the pool threads.

    Args:
        wait: Whether to wait for syncs still running.
    """
    _SYNC_EXECUTOR.shutdown(wait=wait, cancel_futures=True)


def run_sync(payload: garmin_events.SyncRequestedPayload) -> None:
    """Run one queued sync. Blocking; call it from a worker, never a request.

    Args:
        payload: What to sync.
    """
    if payload.kind == garmin_constants.SyncKind.GEAR:
        garmin_gear_service.get_user_gear(payload.user_id)
    elif payload.start_date is not None and payload.end_date is not None:
        garmin_health_service.sync_health_for_dates(payload.start_date, payload.end_date, payload.user_id)


def _log_failure(future: Future) -> None:
    """Log an exception raised by a sync on the in-process pool."""
    exc = future.exception()
    if exc is not None:
        logger.error("Garmin Connect sync failed", exc_info=exc)


def _queue(
    user_id: int,
    kind: garmin_constants.SyncKind,
    start_date: date | None,
    end_date: date | None,
    db: Session,
) -> None:
    """Hand a sync to a worker, or to the in-process pool without durable jobs.

    Args:
        user_id: The user to sync.
        kind: What to pull.
        start_date: First day of the range, for a health sync.
        end_date: Last day of the range, for a health sync.
        db: Database session.
    """
    if core_config.settings.JOBS_ENABLED:
        garmin_event_publishers.publish_sync_requested(user_id, kind, start_date, end_date, db, commit=db.commit)
        logger.info("Garmin Connect sync queued for a worker", extra=core_logger.context(user_id=user_id, kind=kind))
        return
    payload = garmin_events.SyncRequestedPayload(user_id=user_id, kind=kind, start_date=start_date, end_date=end_date)
    future = _SYNC_EXECUTOR.submit(contextvars.copy_context().run, run_sync, payload)
    future.add_done_callback(_log_failure)
    logger.info(
        "Garmin Connect sync queued on the in-process pool", extra=core_logger.context(user_id=user_id, kind=kind)
    )


def request_gear_sync(user_id: int, db: Session) -> garmin_schema.GarminDetail:
    """Queue a sync of the user's Garmin Connect gear.

    Args:
        user_id: The user to sync.
        db: Database session.

    Returns:
        The acknowledgement.
    """
    _queue(user_id, garmin_constants.SyncKind.GEAR, None, None, db)
    return garmin_schema.GarminDetail(detail=f"Garmin Connect gear will be processed in the background for {user_id}")


def request_health_sync(user_id: int, start_date: date, end_date: date, db: Session) -> garmin_schema.GarminDetail:
    """Queue a sync of the user's Garmin Connect health data for a range of days.

    Args:
        user_id: The user to sync.
        start_date: First day of the range.
        end_date: Last day of the range.
        db: Database session.

    Returns:
        The acknowledgement.

    Raises:
        InvalidInputError: When ``start_date`` is after ``end_date`` or the range is longer than
            ``MAX_HEALTH_RANGE_DAYS``.
    """
    if start_date > end_date:
        raise core_exceptions.InvalidInputError("start_date must not be after end_date")
    if end_date - start_date >= timedelta(days=garmin_constants.MAX_HEALTH_RANGE_DAYS):
        raise core_exceptions.InvalidInputError(
            f"The date range must not exceed {garmin_constants.MAX_HEALTH_RANGE_DAYS} days"
        )
    _queue(user_id, garmin_constants.SyncKind.HEALTH, start_date, end_date, db)
    return garmin_schema.GarminDetail(
        detail=f"Garmin Connect health data will be processed in the background for {user_id}"
    )
