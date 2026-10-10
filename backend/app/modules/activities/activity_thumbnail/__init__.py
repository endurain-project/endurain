"""Activity map-thumbnail subsystem.

Owns the thumbnail artifact end to end and reacts to the activity domain events
``activity.created`` / ``activity.deleted``:

- :mod:`render` — pure rendering + storage addressing (key/URL) primitives.
- :mod:`service` — generate/persist, the scheduled backfill, full regeneration,
  and deletion, all through the platform ``StorageProvider`` / ``LockProvider``.
- :mod:`subscribers` — the event handlers and their registration.

No module here is imported by the activity router or by ``store_activity``; those
producers only publish facts, keeping the thumbnail subsystem decoupled.
"""
