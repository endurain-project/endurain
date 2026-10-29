"""Application steps the health packages run identically on their per-user records.

The service-layer counterpart of :mod:`modules.health.record_crud`: committing a staged write under the
version-race guard, and charting a metric over an interval. A package passes the :class:`RecordSpec` its
``crud`` describes the record with, and the callables that stage or read what is specific to it.
"""

from collections.abc import Callable
from datetime import date

from sqlalchemy.orm import Session

import core.etag as core_etag
import core.logger as core_logger
import modules.health.computation as health_computation
import modules.health.constants as health_constants
import modules.health.record_crud as health_record_crud
import modules.health.schema as health_schema
import modules.users.users.integration_service as users_integration

logger = core_logger.get_logger(__name__)


def commit_write[ResultT](
    spec: health_record_crud.RecordSpec,
    record_id: int,
    user_id: int,
    write: Callable[[], ResultT],
    db: Session,
    *,
    log_message: str,
) -> ResultT:
    """Run a staged write to a user's record, commit it and log the change.

    Args:
        spec: The record type.
        record_id: The record the write changes.
        user_id: The record's owner.
        write: Stages the write.
        db: Database session.
        log_message: What the committed write did, logged at INFO.

    Returns:
        What ``write`` returned.

    Raises:
        NotFoundError: If the user has no such record, or it was deleted before the commit.
        PreconditionFailedError: If the record changed since the client read it.
    """
    with core_etag.refuse_stale_write(
        db, spec.etag_label, lambda: health_record_crud.exists(spec, record_id, user_id, db), spec.not_found
    ):
        result = write()
        db.commit()
    logger.info(log_message, extra=core_logger.context(user_id=user_id, record_id=record_id))
    return result


def chart(
    user_id: int,
    interval: health_constants.Interval,
    fetch: Callable[[date, health_constants.ChartBucket], list[health_schema.HealthChartPoint]],
    db: Session,
) -> health_schema.HealthChartSeries:
    """Chart a user's metric over an interval in the finest bucket that keeps it readable.

    Args:
        user_id: The records' owner.
        interval: The window to chart.
        fetch: Reads the metric's points from the given first day, aggregated in the given bucket.
        db: Database session.

    Returns:
        The interval's buckets, one point per bucket that holds a value.
    """
    since = health_computation.get_start_date_for_interval(interval.value, users_integration.local_today(user_id, db))
    bucket, points = health_computation.chart_points(lambda bucket: fetch(since, bucket))
    return health_schema.HealthChartSeries(bucket=bucket, points=points)
