"""The activities core: the activity row itself, and the seams around it.

Deliberately free of any knowledge of *where* an activity came from. It exposes
the format- and provider-agnostic ``ParsedActivity`` contract plus
``ingestion_service.store_parsed_activity``, and never imports a file parser or
a Strava/Garmin client — all of that lives in the sibling ``activity_ingestion``
package. ``integration_service`` is the counterpart surface other modules read,
re-gear, aggregate and bulk-delete through.

Importing this package does not pull in its ORM, CRUD or services: reach for
the submodule you need (``.crud``, ``.schema``, ``.service``, ``.router``). A
re-export facade here would hand out the ORM model and the CRUD functions under
a package path, which is a silent bypass of the boundaries the import-linter
contracts enforce against ``*.models`` and ``*.crud``.
"""
