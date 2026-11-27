"""Sync module: what changed in a user's records since a cursor, for a client that keeps a local copy.

Each module that owns synced records keeps their ``updated_at`` and their tombstones (see :mod:`core.sync`) and
publishes them through its ``integration_service``; this module merges them into one ordered walk and serves
``GET /sync``. No module imports it; ``__init__`` exports nothing.
"""
