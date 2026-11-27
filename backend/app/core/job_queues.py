"""The named durable-job queues and how long a pass of long work on one may run.

The queues are the ones a subscriber is registered on and a dedicated worker serves.

A worker claims a batch of jobs and runs them one after another, so a batch of slow jobs holds it for as long as
they take. Each kind of slow work has a queue of its own, so a deployment can give it workers of its own
(``JOBS_QUEUES``) and it never holds up another kind:

- :data:`DEFAULT`: the work a user waits on, which is short.
- :data:`BACKGROUND`: long work a user asked for and waits to finish (a bulk import, a profile export or import, a
  gear or account deletion).
- :data:`ENRICHMENT`: work derived from a stored activity that calls an outside provider at the provider's pace
  (a map thumbnail, reverse geocoding, which waits for its turn under the configured rate limit), which nobody waits
  on.
"""

from jasil.jobs.registry import DEFAULT_QUEUE

import core.config as core_config

#: Work a user waits on: an upload's import, a provider sync, an email, a notification.
DEFAULT = DEFAULT_QUEUE
#: Long work a user asked for and waits to finish.
BACKGROUND = "background"
#: Derived work that calls an outside provider at its pace, which nobody waits on.
ENRICHMENT = "enrichment"
#: Every queue a subscriber is registered on, which ``JOBS_QUEUES`` may name.
ALL: tuple[str, ...] = (DEFAULT, BACKGROUND, ENRICHMENT)

#: Shortest time budget of one durable pass of long work, in seconds.
PASS_MIN_SECONDS = 30

#: A durable pass of long work lasts at most this fraction of the job lease.
PASS_LEASE_FRACTION = 3


def durable_pass_seconds() -> float:
    """Return the time budget of one pass of long work on a durable worker, which then continues the same job.

    Returns:
        A fraction of ``JOBS_LEASE_SECONDS``, never below ``PASS_MIN_SECONDS``, so a pass ends before its lease does
        and is never mistaken for a dead worker.
    """
    return float(max(PASS_MIN_SECONDS, core_config.settings.JOBS_LEASE_SECONDS // PASS_LEASE_FRACTION))
