"""The named durable-job queues a subscriber is registered on and a dedicated worker serves.

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

#: Work a user waits on: an upload's import, a provider sync, an email, a notification.
DEFAULT = DEFAULT_QUEUE
#: Long work a user asked for and waits to finish.
BACKGROUND = "background"
#: Derived work that calls an outside provider at its pace, which nobody waits on.
ENRICHMENT = "enrichment"
#: Every queue a subscriber is registered on, which ``JOBS_QUEUES`` may name.
ALL: tuple[str, ...] = (DEFAULT, BACKGROUND, ENRICHMENT)
