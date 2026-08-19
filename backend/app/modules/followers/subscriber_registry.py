"""Single registration surface for the followers module's event subscribers.

The counterpart of :mod:`modules.activities.subscriber_registry`, and the reason
both exist: the API lifespan (:func:`main.startup_event`) and the standalone
durable-job worker (:func:`worker.run_worker_process`) each have to register the
same handlers, and a handler added to one entrypoint but not the other leaves its
claimed jobs unresolvable and dead-lettered wherever they are claimed. Naming one
surface per module means the two entrypoints import the same list rather than two
hand-maintained copies of it.

It is also what keeps ``subscribers`` package-private. The entrypoints used to
import ``modules.followers.subscribers`` directly — a reach past the module's
published surface into the file that happens to hold the handlers today.
"""

import modules.followers.subscribers as followers_subscribers
from infra.jobs.registry import JobHandlerRegistry
from infra.providers import EventBusProvider


def register_all_follower_bus_subscribers(events: EventBusProvider) -> None:
    """Register every followers event-bus subscriber on the running bus.

    Called once at startup (the API lifespan) before the event bus is started.
    On the in-process bus these run inline; on the Redis-Streams bus a consumer
    runs them at-least-once.

    Args:
        events: The event-bus provider to subscribe the handlers on.

    Returns:
        None.
    """
    followers_subscribers.register_follower_notification_subscribers(events)


def register_all_follower_durable_handlers(registry: JobHandlerRegistry) -> None:
    """Register every followers durable-job handler on the registry.

    Used by **both** the API lifespan and the standalone worker so a handler is
    never registered in one entrypoint but not the other. Harmless when durable
    jobs are disabled (the registry is simply never consulted).

    Args:
        registry: The durable-subscriber registry to register the handlers on.

    Returns:
        None.
    """
    followers_subscribers.register_follower_notification_durable_handlers(registry)
