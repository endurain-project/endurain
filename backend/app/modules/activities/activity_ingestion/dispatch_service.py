"""The one place ingestion decides how a queued job gets run.

Two deployment profiles exist, and which one is active is a fact about the
deployment, not about a request:

* **Durable** (``JOBS_ENABLED``): the job is staged in the transactional outbox
  with the job row and a worker claims it. A failed attempt is retried and
  dead-lettered by the worker, so the job body only has to raise.
* **Local** (default): there is no worker. The job row is committed and the same
  job body runs on the in-process pool in :mod:`.background`. Nothing retries it,
  so a failure has to leave the job in a terminal state itself.

``service`` states *what* is queued and calls these three functions; it does not
read the setting. The job bodies are identical in both profiles.
"""

from collections.abc import Callable
from datetime import timedelta
from typing import Any

from sqlalchemy.orm import Session

import core.config as core_config
import core.logger as core_logger
import modules.activities.activity_ingestion.background as activity_ingestion_background

logger = core_logger.get_logger(__name__)


def worker_retries() -> bool:
    """Return whether a durable worker retries a job that raises.

    Returns:
        True on the durable profile; False when the in-process pool runs the job
        and nothing will retry it.
    """
    return core_config.settings.JOBS_ENABLED


def claim_lease() -> timedelta:
    """Return how long a ``processing`` claim stays valid without being touched.

    Returns:
        ``JOBS_LEASE_SECONDS``: a job last touched longer ago than the lease has
        been requeued by the runner, so its previous owner is presumed gone. The
        age is measured against the database clock (see
        :func:`activity_ingestion_crud.mark_processing`), never a replica's own.
    """
    return timedelta(seconds=core_config.settings.JOBS_LEASE_SECONDS)


def commit_or_publish(db: Session, *, publish: Callable[[Callable[[], None]], None]) -> None:
    """Make a staged job row durable and, on the durable profile, hand it to the worker.

    Args:
        db: The session holding the staged job row(s).
        publish: Publishes the work event, given the commit callable the
            publisher must own so the outbox row commits with the job row. Not
            called on the local profile.
    """
    durable = worker_retries()
    logger.debug("Making a staged ingestion job durable", extra=core_logger.context(durable=durable))
    if durable:
        publish(db.commit)
    else:
        db.commit()


def run_in_background(run: Callable[..., Any], *args: Any) -> None:
    """Run a job body on the in-process pool, unless a durable worker will.

    Call after the job row is committed.

    Args:
        run: The job body.
        *args: Arguments for the job body.
    """
    if not worker_retries():
        activity_ingestion_background.submit(run, *args)


def run_on_this_node(run: Callable[..., Any], *args: Any) -> None:
    """Run node-bound work on the in-process pool, whatever the profile.

    For work that needs something only this process can see — a folder the user
    dropped files into — so a durable worker on another node could not do it.

    Args:
        run: The job body.
        *args: Arguments for the job body.
    """
    activity_ingestion_background.submit(run, *args)
