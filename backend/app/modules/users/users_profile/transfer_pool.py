"""The pool a profile import or export runs on when no durable worker runs it.

An archive can hold up to 500 MB and take minutes, so these jobs get a pool of their own rather than the
shared subscriber pool, where they would hold the threads that deliver notifications and thumbnails.
"""

import core.local_pool as core_local_pool
import modules.users.users_profile.constants as profile_constants

pool = core_local_pool.BoundedPool(
    "profile-transfer",
    workers=profile_constants.TRANSFER_POOL_WORKERS,
    max_pending=profile_constants.TRANSFER_POOL_MAX_PENDING,
)
