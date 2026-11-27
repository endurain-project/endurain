"""Retained activity-source-file storage subsystem.

Owns the durable copy of each activity's original source file (the parsed
``.gpx`` / ``.tcx`` / ``.fit``) end to end: a row in ``activity_files`` (owner,
SHA-256, key, size, state) and a blob in the platform ``StorageProvider``, so the
same code serves a local disk or remote object storage without change. A user has
one live row per SHA-256, which every activity imported from those bytes shares.
The activity core holds only the row's opaque id; this package sits above it.

- :mod:`integration_service` — stage a file, attach it to the activity being
  stored, read it and remove it; the surface ``activity_ingestion``, reprocess and
  the profile export/import call.
- :mod:`service` — the file lifecycle (``pending``, ``attached``, ``deleting``),
  the daily sweep and the erasure of a user's files.
- :mod:`crud`, :mod:`models`, :mod:`serializers` — the ``activity_files`` table.
- :mod:`subscribers` — the ``activity.deleted`` cleanup handler and registration.
- :mod:`subscriber_registry` — event wiring called by ``main.py`` and ``worker.py``.

The activity router never touches this module: the delete route only publishes a
fact, which the cleanup subscriber reacts to, keeping the subsystem decoupled
from the activity core.
"""
