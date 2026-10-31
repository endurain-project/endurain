"""Run a provider's activity window: every activity gets its turn, and a failure is reported, not hidden.

A provider fetches a window's activities and handles each one (download, parse, store). The policy for
an activity it cannot handle is the same for every provider, so it lives here once: the activity is
logged and skipped so the rest of the window is stored, and the window's first failure is raised once
the window is done. The refresh job then fails and is retried, and ingestion skips what is already
stored, so a retry resumes where the window left off and an activity that never succeeds is visible
instead of silently dropped.

Two kinds of failure end the window at once instead: the ones the provider names as ``propagate`` (a
rate limit, a rejected token), which every following activity would meet too, and a processor raising
:class:`activity_ingestion_contracts.WindowStoppedError`, for a provider that has already dealt with the cause.
"""

from collections.abc import Callable, Iterable

import core.logger as core_logger
import modules.activities.activity_ingestion.contracts as activity_ingestion_contracts

logger = core_logger.get_logger(__name__)


def run_window[ItemT, ResultT](
    items: Iterable[ItemT],
    process: Callable[[ItemT], ResultT],
    *,
    provider: str,
    user_id: int,
    describe: Callable[[ItemT], dict[str, object]],
    propagate: tuple[type[BaseException], ...] = (),
) -> list[ResultT]:
    """Process each activity of a window and raise the first failure once the window is done.

    Args:
        items: The provider's activities for the window.
        process: Handles one activity and returns what it produced.
        provider: The provider's name, for the log.
        user_id: The user whose window it is, for the log.
        describe: Names an activity for the log, such as its provider id.
        propagate: Failures that end the window at once and are raised as they are.

    Returns:
        What ``process`` returned for each activity it handled.

    Raises:
        BaseException: Whatever ``propagate`` names, as soon as it is raised.
        Exception: The first failure of an activity, after the rest of the window was processed.
    """
    results: list[ResultT] = []
    first_failure: Exception | None = None
    failed = 0
    for item in items:
        try:
            results.append(process(item))
        except activity_ingestion_contracts.WindowStoppedError:
            break
        except propagate:
            raise
        except Exception as err:
            failed += 1
            first_failure = first_failure or err
            logger.warning(
                "An activity could not be processed; the rest of the window continues and the window is retried",
                exc_info=err,
                extra=core_logger.context(provider=provider, user_id=user_id, **describe(item)),
            )
    if first_failure is not None:
        logger.warning(
            "Some activities of the window were not processed",
            extra=core_logger.context(provider=provider, user_id=user_id, failed=failed),
        )
        raise first_failure
    return results
