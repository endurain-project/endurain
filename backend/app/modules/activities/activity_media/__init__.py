"""Activity media sub-module for photos attached to an activity.

Blobs are stored through the platform ``StorageProvider`` and served only by
the token-gated route in ``public_router``; the database holds the storage
key, never a servable path.

This package exports nothing from ``__init__``; other modules use it only through
``integration_service`` (see ``tests/architecture``).
"""
