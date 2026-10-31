"""Pydantic schemas for follower relationships."""

from pydantic import BaseModel, ConfigDict, StrictInt, field_validator

import core.pagination as core_pagination
import modules.followers.constants as followers_constants


class FollowRelationshipRead(BaseModel):
    """Serialized representation of a follow relationship.

    Attributes:
        follower_id: The user who follows (the requester).
        followee_id: The user being followed.
        status: Whether the request is pending or accepted.
    """

    model_config = ConfigDict(from_attributes=True, extra="forbid")

    follower_id: StrictInt
    followee_id: StrictInt
    status: followers_constants.FollowStatus


class FollowRequestAccept(BaseModel):
    """The body of an accept applied to a pending follow request.

    Named for the single transition it expresses. ``accepted`` is the only valid
    one: declining deletes the request rather than parking it in a rejected
    state, so a later request from the same user is a fresh decision instead of
    hitting a tombstone. The field is still required so the accept is explicit in
    the payload rather than implied by the route. Unknown fields are rejected
    (``extra="forbid"``) rather than silently ignored, matching every other
    request-body schema in the activities/followers template modules.

    Attributes:
        status: The target status; only ``accepted`` is valid.
    """

    model_config = ConfigDict(extra="forbid")

    status: followers_constants.FollowStatus

    @field_validator("status")
    @classmethod
    def _only_accept(cls, value: followers_constants.FollowStatus) -> followers_constants.FollowStatus:
        """Reject any status other than ``accepted``.

        Args:
            value: The requested status.

        Returns:
            The status, unchanged.

        Raises:
            ValueError: If the status is not ``accepted``.
        """
        if value is not followers_constants.FollowStatus.ACCEPTED:
            raise ValueError("a follow request can only be accepted; DELETE it to decline")
        return value


class RelationshipRead(BaseModel):
    """The authenticated user's relationship with another user, both directions.

    Attributes:
        outgoing: The authenticated user's follow of the other user, if any.
        incoming: The other user's follow of the authenticated user, if any.
    """

    model_config = ConfigDict(from_attributes=True, extra="forbid")

    outgoing: FollowRelationshipRead | None = None
    incoming: FollowRelationshipRead | None = None


#: One page of follow relationships. Aliases the shared
#: :class:`core.pagination.Page` so the follower lists return the same envelope
#: the activities lists do.
FollowRelationshipPage = core_pagination.Page[FollowRelationshipRead]
