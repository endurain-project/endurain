"""Domain feature modules.

Each subpackage under ``modules`` is a vertical feature slice (models, schema,
crud, router, utils) for one domain: activities, auth, users, gears, health,
followers, garmin, strava, notifications, server_settings, and websocket.

Grouping the domains here — beside the platform substrate (``infra``) and the
leaf cross-cutting utilities (``core``) — makes the application's top-level
layering legible directly from the tree: feature modules, platform, utilities,
plus the ``api`` composition root and the ``main`` / ``worker`` entrypoints.
"""
