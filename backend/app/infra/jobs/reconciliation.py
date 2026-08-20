"""The reconciliation-net contract every durable subscriber is held to.

A durable subscriber reacts to an event to derive state — a thumbnail, HR zones,
a geocoded location. Delivery is at-least-once but never *guaranteed*: a
Redis-Streams consumer can drop a message, a provider can be briefly down, and
some write paths publish no event at all (a profile bulk-restore persists
activities directly). So a subscriber that writes **durable** derived state must
ship a scheduled backfill that re-derives whatever the create path missed.

The declaration lives here, in the platform, rather than in whichever module
happened to need it first. It was formerly defined in the activities composition
namespace, which made the invariant enforceable for exactly one module: any other
module wanting to declare its nets would have had to import activities to borrow
the type. Owning the vocabulary in the substrate lets one conformance test hold
every module to it without coupling bounded contexts.
"""

from collections.abc import Callable
from dataclasses import dataclass


@dataclass(frozen=True)
class DurableSubscriberNet:
    """A durable subscriber's reconciliation net, or a documented exemption.

    Exactly one of ``backfill`` / ``exempt_reason`` is set. Neither is not an
    option: a subscriber with no net and no stated reason is one whose derived
    state silently goes missing, which is the failure this declaration exists to
    make impossible to introduce by omission.

    Attributes:
        subscriber_id: The stable durable-subscriber id (as registered on the
            :class:`infra.jobs.registry.JobHandlerRegistry`).
        backfill: The scheduled, argument-free backfill that re-derives anything
            the create-path handler missed, or ``None`` when the subscriber is
            exempt (its derived state is transient / self-healing).
        exempt_reason: Why no backfill is required, when ``backfill`` is ``None``.
            Must be set for exempt subscribers and unset otherwise.
    """

    subscriber_id: str
    backfill: Callable[[], None] | None
    exempt_reason: str | None = None
