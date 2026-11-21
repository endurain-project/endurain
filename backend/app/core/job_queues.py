"""The named durable-job queues a subscriber is registered on and a dedicated worker serves.

A worker claims a batch of jobs and runs them one after another, so a batch of slow jobs holds it for as long as
they take. Work nobody waits on and that can take long (a map thumbnail, reverse geocoding, a bulk import, a
profile export or import, a gear or account deletion) is registered on :data:`BACKGROUND`, so a deployment can give
it workers of its own (``JOBS_QUEUES``) and the work a user waits on, on :data:`DEFAULT`, never waits behind it.
"""

from jasil.jobs.registry import DEFAULT_QUEUE

#: Work a user waits on: an upload's import, a provider sync, an email, a notification.
DEFAULT = DEFAULT_QUEUE
#: Work nobody waits on that can take long.
BACKGROUND = "background"
#: Every queue a subscriber is registered on, which ``JOBS_QUEUES`` may name.
ALL: tuple[str, ...] = (DEFAULT, BACKGROUND)
