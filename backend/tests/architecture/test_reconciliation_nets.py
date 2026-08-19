"""The reconciliation-net invariant, enforced across every converted module.

A durable subscriber that derives state must either ship a scheduled backfill
re-deriving what the create path missed, or say in writing why it does not need
one. This lived in ``tests/activities/test_subscriber_registry.py`` and checked
exactly one module, because the ``DurableSubscriberNet`` type it asserts on lived
in the activities module: followers registered two durable handlers with no net,
no exemption and nothing to catch it. The type now belongs to
:mod:`infra.jobs.reconciliation`, so the invariant is stated once here and every
module in ``_MODULE_NETS`` is held to it.

Module-specific consequences of a net (what a profile bulk-restore must heal, for
instance) stay in that module's own test; this file only asserts the invariant
every module shares.
"""

from dataclasses import dataclass
from unittest.mock import MagicMock, patch

import pytest

import core.scheduler as core_scheduler
import modules.activities.scheduled_jobs as activity_scheduled_jobs
import modules.activities.subscriber_registry as activity_subscriber_registry
import modules.followers.subscriber_registry as followers_subscriber_registry
from infra.jobs.reconciliation import DurableSubscriberNet
from infra.jobs.registry import JobHandlerRegistry


@dataclass(frozen=True)
class _ModuleNets:
    """A module's durable-subscriber registration and its declared nets.

    Attributes:
        name: The module name, used in assertion messages.
        register: Registers every durable handler the module owns.
        nets: The module's declared reconciliation nets.
        recurring_jobs: The module's scheduled work, or ``None`` when it declares
            none (valid only when no net has a backfill).
    """

    name: str
    register: object
    nets: tuple[DurableSubscriberNet, ...]
    recurring_jobs: object | None


#: Opt-in, like ``_CONVERTED`` in the other architecture tests: a module absent
#: here is visibly outstanding rather than silently exempt.
_MODULE_NETS = (
    _ModuleNets(
        name="activities",
        register=activity_subscriber_registry.register_all_activity_durable_handlers,
        nets=activity_subscriber_registry.ACTIVITY_DURABLE_SUBSCRIBER_NETS,
        recurring_jobs=activity_scheduled_jobs.recurring_jobs,
    ),
    _ModuleNets(
        name="followers",
        register=followers_subscriber_registry.register_all_follower_durable_handlers,
        nets=followers_subscriber_registry.FOLLOWER_DURABLE_SUBSCRIBER_NETS,
        recurring_jobs=None,
    ),
)

_MODULE_IDS = [module.name for module in _MODULE_NETS]


def _registered_ids(module: _ModuleNets) -> frozenset[str]:
    """Return the durable subscriber ids a module registers."""
    registry = JobHandlerRegistry()
    module.register(registry)
    return registry.subscriber_ids()


def _scheduled_functions(recurring_jobs) -> set[object]:
    """Return every callable a module's scheduled work would register."""
    scheduled: set[object] = set()
    fake_scheduler = MagicMock()
    fake_scheduler.running = True  # skip scheduler.start()
    fake_scheduler.add_job.side_effect = lambda func, *args, **kwargs: scheduled.add(func)
    with patch.object(core_scheduler, "scheduler", fake_scheduler):
        core_scheduler.start_scheduler(recurring_jobs())
    return scheduled


@pytest.mark.parametrize("module", _MODULE_NETS, ids=_MODULE_IDS)
class TestReconciliationNetInvariant:
    """Every durable subscriber declares a net or a documented exemption."""

    def test_every_registered_subscriber_is_declared(self, module: _ModuleNets):
        """Registering a durable handler without declaring its net fails here."""
        declared = {net.subscriber_id for net in module.nets}
        assert _registered_ids(module) == declared, module.name

    def test_each_net_declares_a_backfill_xor_an_exemption(self, module: _ModuleNets):
        """A net is either a backfill or a stated reason there is none."""
        for net in module.nets:
            has_backfill = net.backfill is not None
            has_reason = bool(net.exempt_reason)
            assert has_backfill != has_reason, f"{module.name}: {net.subscriber_id}"

    def test_declared_backfills_are_scheduled(self, module: _ModuleNets):
        """A declared-but-unscheduled backfill is a silent, undetectable net."""
        with_backfill = [net for net in module.nets if net.backfill]
        if not with_backfill:
            return
        assert module.recurring_jobs is not None, (
            f"{module.name} declares a reconciliation backfill but no scheduled_jobs to run it"
        )
        scheduled = _scheduled_functions(module.recurring_jobs)
        for net in with_backfill:
            assert net.backfill in scheduled, f"{module.name}: {net.subscriber_id}"
