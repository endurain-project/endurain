"""The platform Redis capability — the single owner of Redis connections.

This is the *only* module in the codebase that imports the ``redis`` package,
and it does so **lazily** (inside :func:`create_redis_client`, with the exception
classes exposed through the module-level :func:`__getattr__`). The platform
``state`` and ``events`` Redis backends import *this* module at their top and
borrow a shared client from :func:`get_shared_client`; because nothing here
touches ``redis`` until a ``redis://`` URI is actually resolved, a ``local``
deployment (or one where ``redis`` is not installed — it is the optional
``distributed`` extra) loads zero Redis.

``get_shared_client`` memoizes clients so the process owns *one* connection per
distinct ``(uri, decode_responses)`` pair: in the common case (only ``REDIS_URL``
configured) the auth/MFA/ticket state and the event bus share a single
``decode_responses=True`` client, while the byte-oriented ``StateProvider`` gets
its own ``decode_responses=False`` client.
"""

from __future__ import annotations

import threading
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from redis import Redis

DEFAULT_REDIS_SOCKET_TIMEOUT_SECONDS: float = 2.0

_LAZY_REDIS_ATTRS = frozenset({"Redis", "RedisError", "ResponseError"})


def __getattr__(name: str) -> Any:
    """Lazily expose the ``redis`` exception/client classes.

    Lets callers write clean top-level ``import infra.redis as
    platform_redis`` and ``except platform_redis.RedisError`` without importing
    ``redis`` until the attribute is actually accessed at runtime (i.e. only on
    the Redis code path). Keeps ``redis`` a genuinely optional dependency.
    """
    if name in _LAZY_REDIS_ATTRS:
        import redis

        return getattr(redis, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def delete_matching_keys(
    redis_client: Any,
    key_pattern: str,
    scan_count: int = 100,
) -> int:
    """
    Delete Redis keys matching a scan pattern in small batches.

    Args:
        redis_client: Redis client used for deletion.
        key_pattern: Redis glob-style key pattern.
        scan_count: Requested Redis SCAN batch size.

    Returns:
        Number of keys deleted.

    Raises:
        RedisError: When Redis scan or delete fails.
    """
    deleted_count = 0
    keys_to_delete: list[str] = []

    for redis_key in redis_client.scan_iter(match=key_pattern, count=scan_count):
        keys_to_delete.append(redis_key)
        if len(keys_to_delete) >= scan_count:
            deleted_count += redis_client.delete(*keys_to_delete)
            keys_to_delete.clear()

    if keys_to_delete:
        deleted_count += redis_client.delete(*keys_to_delete)

    return deleted_count


def create_redis_client(
    storage_uri: str,
    purpose: str,
    socket_timeout: float = DEFAULT_REDIS_SOCKET_TIMEOUT_SECONDS,
    *,
    decode_responses: bool = True,
) -> Redis:
    """
    Create and verify a Redis client.

    Args:
        storage_uri: Redis storage URI.
        purpose: Human-readable use case for error messages.
        socket_timeout: Connection and read timeout in seconds.
        decode_responses: When True (default) responses are decoded to ``str``;
            pass False for byte-oriented callers (e.g. the platform StateProvider)
            that need raw ``bytes`` back.

    Returns:
        Connected Redis client.

    Raises:
        RuntimeError: When Redis cannot be initialized.
    """
    # Imported lazily: ``redis`` is the optional ``distributed`` extra, so this
    # is the single point where the package is actually loaded and only on the
    # Redis code path.
    from redis import Redis, RedisError

    try:
        redis_client = Redis.from_url(
            storage_uri,
            decode_responses=decode_responses,
            socket_connect_timeout=socket_timeout,
            socket_timeout=socket_timeout,
        )
        redis_client.ping()
    except (RedisError, ValueError) as redis_error:
        raise RuntimeError(f"Unable to initialize Redis storage for {purpose}.") from redis_error
    return redis_client


_shared_clients: dict[tuple[str, bool], Redis] = {}
_shared_clients_lock = threading.Lock()


def get_shared_client(
    storage_uri: str,
    *,
    purpose: str,
    decode_responses: bool = True,
) -> Redis:
    """
    Return a process-wide shared Redis client, creating it once per config.

    The platform Redis backends resolve their connection through here so the
    process opens *one* client per distinct ``(storage_uri, decode_responses)``
    pair instead of one per consumer.

    Args:
        storage_uri: Redis storage URI selecting the server.
        purpose: Human-readable use case for connection-error messages.
        decode_responses: Whether the client decodes responses to ``str``.

    Returns:
        The shared, connectivity-verified Redis client for this config.

    Raises:
        RuntimeError: When Redis cannot be initialized.
    """
    client_key = (storage_uri, decode_responses)
    with _shared_clients_lock:
        client = _shared_clients.get(client_key)
        if client is None:
            client = create_redis_client(storage_uri, purpose, decode_responses=decode_responses)
            _shared_clients[client_key] = client
        return client


def reset_shared_clients() -> None:
    """
    Discard the memoized shared clients.

    Intended for tests that patch client creation; production code never needs
    to evict the process-wide clients.

    Raises:
        None.
    """
    with _shared_clients_lock:
        _shared_clients.clear()
