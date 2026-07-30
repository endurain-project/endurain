"""
Followers module for user follow/unfollow relationships.

This module manages follow requests, acceptance, and removal between users,
including notification side effects on creation and acceptance.

Exports:
    - CRUD: get_all_followers_by_user_id, get_accepted_followers_by_user_id,
      get_all_following_by_user_id, get_accepted_following_by_user_id,
      count_followers_by_user_id, count_following_by_user_id,
      get_follower_for_user_id_and_target_user_id,
      create_follower, accept_follower, delete_follower
    - Schemas: Follower, MessageResponse
    - Models: Follower (ORM model)
"""

from .crud import (
    accept_follower,
    count_followers_by_user_id,
    count_following_by_user_id,
    create_follower,
    delete_follower,
    get_accepted_followers_by_user_id,
    get_accepted_following_by_user_id,
    get_all_followers_by_user_id,
    get_all_following_by_user_id,
    get_follower_for_user_id_and_target_user_id,
)
from .models import Follower as FollowerModel
from .schema import Follower, MessageResponse

__all__ = [
    # Pydantic schemas
    "Follower",
    # Database model
    "FollowerModel",
    "MessageResponse",
    "accept_follower",
    "count_followers_by_user_id",
    "count_following_by_user_id",
    "create_follower",
    "delete_follower",
    "get_accepted_followers_by_user_id",
    "get_accepted_following_by_user_id",
    # CRUD operations
    "get_all_followers_by_user_id",
    "get_all_following_by_user_id",
    "get_follower_for_user_id_and_target_user_id",
]
