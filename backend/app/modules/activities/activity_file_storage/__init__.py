"""Retained activity-source-file storage subsystem.

Owns the durable copy of each activity's original source file (the parsed
``.gpx`` / ``.tcx`` / ``.fit``) end to end, addressing it through the platform
``StorageProvider`` exactly like the thumbnail subsystem addresses its rendered
image — so the same code serves a local disk or remote object storage without
change, and file-based ingestion is not tied to the API node's disk.

- :mod:`integration_service` — storage addressing (area/key) plus save/read/delete
  of the retained file through the platform ``StorageProvider``; the surface
  ``activity_ingestion`` and the profile export/import call.
- :mod:`subscribers` — the ``activity.deleted`` cleanup handler and registration.
- :mod:`subscriber_registry` — event wiring called by ``main.py`` and ``worker.py``.

The activity router never touches this module: the delete route only publishes a
fact, which the cleanup subscriber reacts to, keeping the subsystem decoupled
from the activity core.
"""
