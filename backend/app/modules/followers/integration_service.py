"""The followers surface consumed by other modules (activities).

The counterpart of :mod:`modules.activities.activity.integration_service`, and
named to match: every module exposes the operations other modules may use under
``integration_service``, so "what may I depend on?" has one answer everywhere
rather than being ``integration_service`` in one module and ``service`` in the
next.

The distinction is not cosmetic. ``service`` is the module's own application
layer — privacy-checked reads, follow/accept/unfollow writes, the notification
publishes — and most of it is meaningless to a caller outside this module.
``integration_service`` is the small, deliberate subset that is not: today, the
accepted-followee lookup the activities feed and the non-owner visibility filter
are built on.

Enforced by the ``activities-followers-boundary`` import-linter contract: the
activities module must reach followers through here, never through
``followers.crud`` / ``followers.models`` / ``followers.service``.
"""

from sqlalchemy.orm import Session

import modules.followers.crud as followers_crud


def list_accepted_followee_ids(user_id: int, db: Session) -> list[int]:
    """List the ids of users the given user follows (accepted only).

    The read the activities feed and the non-owner visibility filter are built
    on, so the activities module never touches the followers table itself.

    Args:
        user_id: The follower whose accepted followees to list.
        db: Database session.

    Returns:
        The accepted followee user ids (empty list if none).
    """
    return followers_crud.list_accepted_followee_ids(user_id, db)
