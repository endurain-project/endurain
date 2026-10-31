"""ORM↔schema transformation for follow relationships.

``crud`` calls this at its edge so ORM rows never leave the persistence layer.
"""

import modules.followers.models as followers_models
import modules.followers.schema as followers_schema


def to_read_schema(follower: followers_models.Follower) -> followers_schema.FollowRelationshipRead:
    """Convert a Follower ORM row into its serialized DTO.

    Args:
        follower: The ORM row to convert.

    Returns:
        The follow relationship DTO.

    Raises:
        ValidationError: If the row does not satisfy the DTO.
    """
    return followers_schema.FollowRelationshipRead.model_validate(follower)
