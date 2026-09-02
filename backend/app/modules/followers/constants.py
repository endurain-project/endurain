"""Domain constants for follow relationships.

The status vocabulary lived in three places at once: the ``FollowStatus`` enum in
``schema``, ten raw ``"pending"`` / ``"accepted"`` literals in ``crud``, and the
column default in ``models``. The enum was the declared vocabulary and two of the
three layers ignored it.

It lives here rather than in ``schema`` because every layer needs it: ``models``
stamps the default, ``crud`` filters on it, ``service`` compares against it, and
``schema`` types the field clients see. Persistence importing the wire contract
to learn its own column's values is backwards; a constant all four share is not.
"""

from enum import Enum


class FollowStatus(Enum):
    """Status of a follow relationship.

    Attributes:
        PENDING: The follow request has been sent but not yet accepted.
        ACCEPTED: The follow request has been accepted.
    """

    PENDING = "pending"
    ACCEPTED = "accepted"
