"""Activity map-thumbnail subsystem.

Owns the thumbnail artifact end to end and reacts to the activity domain events
``activity.created`` / ``activity.deleted``:

- :mod:`render` — pure map rendering to WebP bytes.
- :mod:`signing` — storage addressing (key/area) and signed capability URLs/tokens.
- :mod:`service` — generate/persist, serve, the scheduled backfill, full
  regeneration, and deletion, all through the platform ``StorageProvider`` /
  ``LockProvider``.
- :mod:`subscribers` — the event handlers; registered via :mod:`subscriber_registry`.

The activity package never imports this one: producers only publish facts, and
the thumbnail URL resolver is installed by app composition through the activities
``contributor_registry``.
"""
