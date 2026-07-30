"""Concrete backends implementing the platform providers.

Holds both the process-local backends (memory state, local-filesystem storage,
in-process event bus, no-op lock, system clock) used by the default ``local``
profile and the distributed backends (Redis, S3, Redis Streams, Postgres
advisory lock) selected under the ``distributed`` profile.

Backends are the only place infrastructure clients (redis, boto3) may be
imported — enforced by the import-linter contract.
"""
