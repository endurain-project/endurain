"""Inter-module data shapes for follow-network reads."""

from dataclasses import dataclass


@dataclass(frozen=True)
class ProfileFollowCounts:
    """Accepted follower and following counts visible to a profile viewer.

    Attributes:
        followers: Number of accepted followers.
        following: Number of accepted followees.
    """

    followers: int
    following: int
