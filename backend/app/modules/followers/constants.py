"""Domain constants for follow relationships.

The status vocabulary is stated once, here, rather than as raw ``"pending"`` /
``"accepted"`` literals in each layer.

It lives here rather than in ``schema`` because every layer needs it: ``models``
stamps the default, ``crud`` filters on it, ``service`` compares against it, and
``schema`` types the field clients see. Persistence importing the wire contract
to learn its own column's values is backwards; a constant all four share is not.
"""

from enum import StrEnum


class FollowStatus(StrEnum):
    """Status of a follow relationship.

    Attributes:
        PENDING: The follow request has been sent but not yet accepted.
        ACCEPTED: The follow request has been accepted.
    """

    PENDING = "pending"
    ACCEPTED = "accepted"


#: Follow requests a user may have waiting for their decision. Past it, new requests are refused, so a
#: script cannot flood one user with requests and notifications.
MAX_PENDING_REQUESTS = 200
