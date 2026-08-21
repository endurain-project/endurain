"""Pydantic schemas for follower relationships."""

from pydantic import BaseModel, ConfigDict, StrictInt, field_validator

import core.pagination as core_pagination
from modules.followers.constants import FollowStatus


class FollowRelationship(BaseModel):
    """Serialized representation of a follow relationship."""

    model_config = ConfigDict(from_attributes=True, extra="forbid")

    follower_id: StrictInt
    followee_id: StrictInt
    status: FollowStatus


class FollowRequestAccept(BaseModel):
    """The body of an accept applied to a pending follow request.

    Named for the single transition it expresses. ``accepted`` is the only valid
    one: declining deletes the request rather than parking it in a rejected
    state, so a later request from the same user is a fresh decision instead of
    hitting a tombstone. The field is still required so the accept is explicit in
    the payload rather than implied by the route. Unknown fields are rejected
    (``extra="forbid"``) rather than silently ignored, matching every other
    request-body schema in the activities/followers template modules.
    """

    model_config = ConfigDict(extra="forbid")

    status: FollowStatus

    @field_validator("status")
    @classmethod
    def _only_accept(cls, value: FollowStatus) -> FollowStatus:
        if value is not FollowStatus.ACCEPTED:
            raise ValueError("a follow request can only be accepted; DELETE it to decline")
        return value


class RelationshipView(BaseModel):
    """The authenticated user's relationship with another user, both directions.

    Attributes:
        outgoing: The authenticated user's follow of the other user, if any.
        incoming: The other user's follow of the authenticated user, if any.
    """

    model_config = ConfigDict(from_attributes=True, extra="forbid")

    outgoing: FollowRelationship | None = None
    incoming: FollowRelationship | None = None


#: One page of follow relationships. Aliases the shared
#: :class:`core.pagination.Page` so the follower lists return the same envelope
#: the activities lists do — they previously returned bare, unbounded arrays,
#: which made the two template modules disagree on what a list response is.
FollowRelationshipPage = core_pagination.Page[FollowRelationship]
