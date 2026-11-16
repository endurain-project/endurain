"""The COROS surface consumed by other modules."""

from sqlalchemy.orm import Session

import modules.coros.crud as coros_crud


def is_linked(user_id: int, db: Session) -> bool:
    """Return whether a user has a connected COROS account.

    Args:
        user_id: User to check.
        db: Database session.

    Returns:
        True when a COROS access token is stored for the user.
    """
    return coros_crud.is_linked(user_id, db)
