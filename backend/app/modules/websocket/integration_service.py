"""The websocket surface consumed by other modules.

Callers want one thing: "tell this user's browser something changed". They publish a
hint on the platform's realtime channel, which reaches every process; the one holding
the user's socket (see ``subscribers``) pushes it, and the others drop it.

**A hint is never the record.** The caller has already written whatever durable row the
client will see on its next fetch, and the client refetches on a hint. Delivery is
best-effort and at-most-once: a hint can be lost, so nothing may depend on one arriving.
That is why this never raises over a push that could not be sent.
"""

import jasil.runtime as platform_runtime

import core.logger as core_logger
import modules.websocket.keys as websocket_keys

logger = core_logger.get_logger(__name__)


def push_to_user(user_id: int, message: dict) -> None:
    """Publish a hint for one user to every process, from any thread.

    Safe from a process that holds no sockets, such as the job worker. A transport
    failure is dropped by the channel itself. A message the channel refuses (not
    JSON, over its size cap) is a bug in the caller; it is logged and dropped rather
    than failing the work that triggered the push.

    Args:
        user_id: The target user.
        message: A small JSON-serializable hint, such as the event name and an id.
    """
    if not platform_runtime.is_platform_active():
        logger.debug("The platform is not running; dropped a realtime push", extra=core_logger.context(user_id=user_id))
        return
    try:
        platform_runtime.get_active_platform().realtime.notify(websocket_keys.user_key(user_id), message)
    except ValueError:
        logger.error(
            "The realtime channel refused a push; the durable record is unaffected",
            exc_info=True,
            extra=core_logger.context(user_id=user_id),
        )
