"""The health domain: everything about a user's body and daily habits.

A composition namespace of independent packages rather than one flat module, because
health is several aggregates: ``health_sleep``, ``health_weight``, ``health_steps``,
``health_fasting``, ``health_water``, ``health_poop`` and ``health_targets``, plus the
read-only ``health_dashboard`` that consolidates today's values.

The namespace publishes only ``constants`` (the shared ``Interval`` enum),
``computation`` (pure date and SQL helpers) and ``schema`` (the shared list-response
base). The structure and import rules are in ``docs/developer-guide/module-structure.md``.
Importing this package pulls in nothing; reach for the sub-package you need.
"""
