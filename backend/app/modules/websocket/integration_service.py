"""The websocket surface consumed by other modules.

Callers want one thing — "push this to that user's browser if they are looking"
— and had to assemble it from two internals: the process-local connection
registry (``manager``) and the send helper (``utils``, which raises an HTTP error
on one specific message type, meaningless to a background job). This states the
whole thing as one best-effort operation.

**Best-effort by contract.** A push is a live convenience, never the record: the
caller has already written whatever durable row the client will see on its next
fetch. So a user with no open connection, a closed socket, or a send failure all
return False rather than raising.

Known limitation (distributed): the registry is **process-local**, so this
reaches only clients whose socket is held by this process. In a multi-replica
deployment a push issued from another replica is silently dropped for that
client. Cross-replica fan-out belongs to the websocket module rework; it is
recorded here because this is now the one place every caller goes through.
"""

import core.logger as core_logger
import modules.websocket.manager as websocket_manager

logger = core_logger.get_logger(__name__)


async def push_to_user(user_id: int, message: dict) -> bool:
    """
    Send a JSON message to each of a user's open websockets, if they have any.

    Args:
        user_id: The target user.
        message: JSON-serializable payload.

    Returns:
        True when the message was handed to at least one open connection, False when
        the user has none in this process or every send failed.

    Raises:
        None.
    """
    connections = websocket_manager.get_websocket_manager().get_connections(user_id)
    if not connections:
        # TODO(websocket rework): when the user's socket is held by another API replica, or the
        # caller is a dedicated worker, publish the push on the event bus so the process that owns
        # the connection delivers it. Until then the live push is dropped here (the notification
        # row is unaffected).
        logger.debug("No websocket connection for the user in this process", extra=core_logger.context(user_id=user_id))
        return False
    failures = await websocket_manager.send_json_to_all(connections, message)
    for err in failures:
        logger.debug(
            "Websocket push failed; the durable record is unaffected",
            exc_info=err,
            extra=core_logger.context(user_id=user_id),
        )
    return len(failures) < len(connections)
