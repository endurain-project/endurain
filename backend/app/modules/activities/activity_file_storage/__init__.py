"""Retained activity-source-file storage subsystem.

Owns the durable copy of each activity's original source file (the parsed
``.gpx`` / ``.tcx`` / ``.fit``) end to end, addressing it through the platform
``StorageProvider`` exactly like the thumbnail subsystem addresses its rendered
image — so the same code serves a local disk or remote object storage without
change, and file-based ingestion is no longer pinned to the API node's disk.

- :mod:`service` — storage addressing (area/key) plus save/read/delete of the
  retained file through the platform ``StorageProvider``.
- :mod:`subscribers` — the ``activity.deleted`` cleanup handler and registration.

No module here is imported by the activity router or by ``store_activity``; the
ingestion orchestrator writes the file and the delete route only publishes a
fact, keeping the subsystem decoupled from the activities core.
"""
