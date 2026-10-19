"""The activities core: the activity row itself, and the seams around it.

Deliberately free of any knowledge of *where* an activity came from. It exposes
the format- and provider-agnostic ``ParsedActivity`` contract plus
``ingestion_service.store_parsed_activity``, and never imports a file parser or
a Strava/Garmin client — all of that lives in the sibling ``activity_ingestion``
package. ``integration_service`` is the counterpart surface other modules read,
re-gear, aggregate and bulk-delete through.

This package exports nothing from ``__init__``; other modules use it only through
``integration_service`` (see ``tests/architecture``).
"""
