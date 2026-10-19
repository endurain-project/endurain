"""The followers surface other modules may call.

Today that is the accepted-followee lookup the activities feed and visibility filter
are built on. The follow graph itself stays behind ``service``, which privacy-checks
every read.
"""

from sqlalchemy.orm import Session

import modules.followers.crud as followers_crud


def list_accepted_followee_ids(user_id: int, db: Session) -> list[int]:
    """List the ids of users the given user follows (accepted only).

    The read the activities feed and the non-owner visibility filter are built
    on, so the activities module never touches the followers table itself.

    Memoized for the life of the session by the CRUD layer: one request asks this
    repeatedly — a paginated list resolves it once for the page and again for the
    total, and an activity detail page asks once per child resource through the
    visibility gate.

    Args:
        user_id: The follower whose accepted followees to list.
        db: Database session.

    Returns:
        The accepted followee user ids (empty list if none).
    """
    return followers_crud.list_accepted_followee_ids(user_id, db)
