"""The activities domain: everything about a recorded activity.

A composition namespace of independent packages rather than one flat module, because an
activity is several aggregates: the row and its summaries (``activity``), its child
resources (``activity_laps``, ``activity_sets``, ``activity_streams``,
``activity_workout_steps``, ``activity_media``, ``activity_exercise_titles``), the
derived artifacts (``activity_thumbnail``, ``activity_geocoding``) and the paths data
arrives on (``activity_ingestion``, ``activity_file_import``, ``activity_file_storage``).

The structure and import rules are in ``docs/developer-guide/module-structure.md``.
Importing this package pulls in nothing; reach for the sub-package you need.
"""
