"""Domain event channels owned by the followers module.

Channel names (``event_type`` values) are owned by the publishing domain, not the
platform substrate. The follow service publishes the facts below; the follower
notification subscriber reacts by subscribing to the same constants, so producer
and subscriber cannot drift on the string. Convention: ``<domain>.<fact>``, past
tense.
"""

from typing import ClassVar

from jasil.event_versioning import VersionedPayload
from pydantic import ConfigDict

# Published after a follow-request row has been created (a user requests to
# follow another user), so the target user can be notified.
FOLLOWER_REQUESTED = "follower.requested"

# Published after a pending follow request has been accepted, so the original
# requester can be notified that their request was accepted.
FOLLOWER_ACCEPTED = "follower.accepted"

# Published after a pending follow request has been removed without being accepted
# (the target declined it or the requester withdrew it), so the "wants to follow you"
# notification that announced it can be taken away.
FOLLOWER_REQUEST_REMOVED = "follower.request_removed"


class FollowerRequestedPayload(VersionedPayload):
    """Validated payload for the ``follower.requested`` event.

    Subscribers validate against this schema so a malformed payload raises at the
    boundary — with the offending fields named — instead of being silently
    dropped by ad-hoc type checks.

    Attributes:
        requester_user_id: The user who requested to follow.
        target_user_id: The user being followed (who is notified).
    """

    model_config = ConfigDict(extra="ignore")

    SCHEMA_VERSION: ClassVar[int] = 1

    requester_user_id: int
    target_user_id: int


class FollowerAcceptedPayload(VersionedPayload):
    """Validated payload for the ``follower.accepted`` event.

    Attributes:
        accepter_user_id: The user who accepted the request.
        requester_user_id: The original requester (who is notified).
    """

    model_config = ConfigDict(extra="ignore")

    SCHEMA_VERSION: ClassVar[int] = 1

    accepter_user_id: int
    requester_user_id: int


class FollowerRequestRemovedPayload(VersionedPayload):
    """Validated payload for the ``follower.request_removed`` event.

    Attributes:
        requester_user_id: The user whose follow request was removed.
        target_user_id: The user the request was addressed to (who owns the notification).
    """

    model_config = ConfigDict(extra="ignore")

    SCHEMA_VERSION: ClassVar[int] = 1

    requester_user_id: int
    target_user_id: int
