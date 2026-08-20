"""The activities domain: everything about a recorded activity.

Organised as sub-packages rather than one flat module because an activity is
several aggregates, not one: the activity row and its summary projections
(``activity``), its child resources (``activity_laps``, ``activity_sets``,
``activity_streams``, ``activity_workout_steps``, ``activity_media``), the
derived artifacts (``activity_thumbnail``, ``activity_geocoding``), and the
paths data arrives on (``activity_ingestion``, ``activity_file_import``,
``activity_file_storage``). A module with a single aggregate — ``followers`` —
stays flat.

Every sub-package follows the same layering: ``router`` / ``public_router``
delegate to ``service``, which decides access and orchestrates, and ``crud`` is
the only file that touches the ORM. ``integration_service`` is the sole surface
other modules may consume. The import-linter contracts in ``backend/.importlinter``
enforce that shape structurally, by wildcard, so a new sub-package inherits the
rules instead of having to opt in.

Importing this package pulls in nothing: reach for the sub-package you need. A
re-export facade here would hand out ORM models and CRUD functions under a
package path, which is a silent bypass of those same contracts.
"""
