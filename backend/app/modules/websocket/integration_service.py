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
    Send a JSON message to a user's open websocket, if they have one.

    Args:
        user_id: The target user.
        message: JSON-serializable payload.

    Returns:
        True when the message was handed to an open connection, False when the
        user has none in this process or the send failed.

    Raises:
        None.
    """
    websocket = websocket_manager.get_websocket_manager().get_connection(user_id)
    if websocket is None:
        logger.debug("No websocket connection for the user in this process", extra=core_logger.context(user_id=user_id))
        return False
    try:
        await websocket.send_json(message)
    except Exception as err:
        logger.debug(
            "Websocket push failed; the durable record is unaffected",
            exc_info=err,
            extra=core_logger.context(user_id=user_id),
        )
        return False
    return True
